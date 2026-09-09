/**
 * Copyright 2020 The Department of Interior
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License. You may obtain a copy of
 * the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations under
 * the License.
 */
package net.geoprism.geoai.explorer.core.service;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

import jakarta.annotation.PreDestroy;
import net.geoprism.geoai.explorer.core.model.GenericRestException;
import net.geoprism.geoai.explorer.core.model.JobStatusResponse;

/**
 * Runs long-lived requests (chat prompts and location lookups) on a
 * background thread and hands the caller a job id to poll, instead of
 * blocking the HTTP request thread until the work finishes.
 *
 * These requests invoke a Bedrock AgentCore harness which can take up to
 * several minutes to respond -- comfortably longer than the ALB's 60
 * second idle timeout, which was causing 504 Gateway Timeout errors.
 * Returning immediately with a job id (a 202 Accepted) lets the controller
 * respond in milliseconds while the work continues in the background; the
 * client is expected to poll {@link #getStatus(String)} until the job
 * reports SUCCEEDED or FAILED.
 *
 * Job state is held in memory on this instance. That is sufficient as long
 * as this service runs as a single instance (or behind an ALB with sticky
 * sessions) -- if it is ever horizontally scaled without sticky sessions,
 * this store should move to a shared backing store (e.g. a database or
 * ElastiCache) so a poll doesn't land on an instance that never ran the
 * job.
 */
@Service
public class AsyncJobService
{
  private static final Logger log = LoggerFactory.getLogger(AsyncJobService.class);

  /*
   * How long a completed job's result is retained so a client that is slow
   * to poll (or briefly loses connectivity) can still collect it. This
   * comfortably covers the longest expected request plus polling latency.
   */
  private static final long RETENTION_MILLIS = 30 * 60 * 1000L;

  public enum Status
  {
    PENDING, RUNNING, SUCCEEDED, FAILED
  }

  private final Map<String, Job> jobs = new ConcurrentHashMap<>();

  /*
   * This service owns its own background thread pool rather than reusing
   * WebConfiguration's "taskExecutor" bean. That bean lives in the web
   * module and exists purely to back Spring MVC's async request handling;
   * depending on it here would pull core services into the web module's
   * application context, which breaks plain core-context tests (like
   * HistoryTest) that never load WebConfiguration. Sized the same as that
   * bean, for the same reasons.
   */
  private final ThreadPoolTaskExecutor executor;

  public AsyncJobService()
  {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(10);
    executor.setQueueCapacity(1000);
    executor.setThreadNamePrefix("async-job-");
    executor.initialize();

    this.executor = executor;
  }

  @PreDestroy
  public void shutdown()
  {
    this.executor.shutdown();
  }

  /**
   * Submits work to run in the background and returns a job id that can be
   * passed to {@link #getStatus(String)} to poll for its outcome.
   */
  public String submit(Supplier<?> task)
  {
    String jobId = UUID.randomUUID().toString();

    Job job = new Job();
    this.jobs.put(jobId, job);

    this.executor.execute(() -> {
      job.status = Status.RUNNING;

      try
      {
        job.result = task.get();
        job.status = Status.SUCCEEDED;
      }
      catch (Exception e)
      {
        log.error("Async job [{}] failed.", jobId, e);

        job.errorMessage = resolveErrorMessage(e);
        job.status = Status.FAILED;
      }
      finally
      {
        job.completedAt = System.currentTimeMillis();
      }
    });

    return jobId;
  }

  /**
   * Returns the current status of a previously submitted job. Safe to call
   * repeatedly while the job is PENDING or RUNNING.
   */
  public JobStatusResponse getStatus(String jobId)
  {
    Job job = this.jobs.get(jobId);

    if (job == null)
    {
      throw new GenericRestException("The requested job could not be found. It may have expired -- please try your request again.");
    }

    return new JobStatusResponse(jobId, job.status.name(), job.result, job.errorMessage);
  }

  private String resolveErrorMessage(Exception e)
  {
    if (e instanceof GenericRestException && e.getMessage() != null && !e.getMessage().isBlank())
    {
      return e.getMessage();
    }

    return "The request was unable to complete. If your chat history is not relevant to the current request, you can try clearing your chat history and sending your message again.";
  }

  /**
   * Periodically evicts completed jobs so this map doesn't grow without
   * bound over the lifetime of the server. Requires @EnableScheduling to
   * be active somewhere in the application context.
   */
  @Scheduled(fixedDelay = 5 * 60 * 1000L)
  public void evictExpiredJobs()
  {
    long cutoff = System.currentTimeMillis() - RETENTION_MILLIS;

    this.jobs.entrySet().removeIf(entry -> {
      Job job = entry.getValue();
      return job.completedAt > 0 && job.completedAt < cutoff;
    });
  }

  private static final class Job
  {
    private volatile Status status      = Status.PENDING;
    private volatile Object result;
    private volatile String errorMessage;
    private volatile long   completedAt = 0;
  }
}
