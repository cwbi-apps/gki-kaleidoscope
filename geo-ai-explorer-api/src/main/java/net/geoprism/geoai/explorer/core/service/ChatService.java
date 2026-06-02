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

import java.time.Duration;
import java.util.Arrays;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import dev.failsafe.Failsafe;
import dev.failsafe.RetryPolicy;
import net.geoprism.geoai.explorer.core.model.GenericRestException;
import net.geoprism.geoai.explorer.core.model.History;
import net.geoprism.geoai.explorer.core.model.LocationPage;
import net.geoprism.geoai.explorer.core.model.Message;

@Service
public class ChatService
{
  private static final Logger log = LoggerFactory.getLogger(ChatService.class);

  @Autowired
  private BedrockService      bedrock;

  @Autowired
  private GraphQueryService   graph;

  public Message prompt(String sessionId, String inputText)
  {
    RetryPolicy<Message> retryPolicy = RetryPolicy.<Message>builder()
        .handle(Exception.class)
        .withMaxAttempts(3)
        .withDelay(Duration.ofMillis(250))
        .onFailedAttempt(event -> {
          Throwable failure = event.getLastException();

          if (failure instanceof UnableToAssistResponseException)
          {
            log.warn(
                "Chat prompt attempt {} returned an unable-to-assist response. Retrying.",
                event.getAttemptCount()
            );
          }
          else
          {
            log.warn(
                "Chat prompt attempt {} failed with exception.",
                event.getAttemptCount(),
                failure
            );
          }
        })
        .build();

    try
    {
      return Failsafe.with(retryPolicy).get(() -> {
        Message message = this.bedrock.prompt(sessionId, inputText);

        if (isUnableToAssistResponse(message))
        {
          throw new UnableToAssistResponseException(message);
        }

        return message;
      });
    }
    catch (UnableToAssistResponseException e)
    {
      log.error("Chat agent returned unable-to-assist response after retries.");

      return e.getMessageResponse();
    }
    catch (Exception e)
    {
      log.error("Error invoking a remote service after retries: ", e);

      throw new GenericRestException("The chat agent was unable to generate a response. If your chat history is not relevant to the current request, you can try clearing your chat history and sending your message again.", e);
    }
  }

  private boolean isUnableToAssistResponse(Message message)
  {
    return message != null &&
        message.getContent() != null &&
        message.getContent().toLowerCase().contains("i am unable to assist");
  }

  public List<LocationPage> getLocations(History history)
  {
    RetryPolicy<List<LocationPage>> retryPolicy = RetryPolicy.<List<LocationPage>>builder()
        .handle(Exception.class)
        .withMaxAttempts(3)
        .withDelay(Duration.ofMillis(250))
        .onFailedAttempt(event -> {
          Throwable failure = event.getLastException();

          if (failure instanceof EmptyLocationPageException)
          {
            log.warn(
                "Location lookup attempt {} returned zero results. Retrying.",
                event.getAttemptCount()
            );
          }
          else
          {
            log.warn(
                "Location lookup attempt {} failed with exception.",
                event.getAttemptCount(),
                failure
            );
          }
        })
        .build();

    try
    {
      return Failsafe.with(retryPolicy).get(() -> {
        String statement = this.bedrock.getLocationSparql(history);
        LocationPage page = this.getPage(statement, null, history.getOffset(), history.getLimit());
        List<LocationPage> pages = Arrays.asList(page);

        if (pages.size() == 0 ||
            pages.stream().mapToInt(p -> p.getLocations().size()).sum() == 0)
        {
          throw new EmptyLocationPageException(pages);
        }

        return pages;
      });
    }
    catch (EmptyLocationPageException e)
    {
      log.info("Location lookup returned zero results after retries.");

      return e.getPages();
    }
    catch (Exception e)
    {
      log.error("Error invoking a bedrock service after retries: ", e);

      throw new GenericRestException(
          "Unable to map the locations. An error occurred while generating the response",
          e
      );
    }
  }

  private static class EmptyLocationPageException extends RuntimeException
  {
    List<LocationPage> pages;
    
    private EmptyLocationPageException(List<LocationPage> pages)
    {
      super("Location lookup returned zero results.");
      this.pages = pages;
    }
    
    public List<LocationPage> getPages() {
      return pages;
    }
  }

  private static class UnableToAssistResponseException extends RuntimeException
  {
    private final Message messageResponse;

    private UnableToAssistResponseException(Message messageResponse)
    {
      super("Chat agent returned unable-to-assist response.");
      this.messageResponse = messageResponse;
    }

    public Message getMessageResponse()
    {
      return messageResponse;
    }
  }

  public LocationPage getPage(String statement, String type, int offset, int limit)
  {
    return this.getPage(statement, type, offset, limit, List.of());
  }

  public LocationPage getPage(String statement, String type, int offset, int limit, List<String> excludedTypes)
  {
    try
    {
      boolean combinedPage = type == null || type.isBlank();
      String pageStatement = combinedPage
          ? this.graph.buildExcludedTypesQuery(statement, excludedTypes)
          : this.graph.buildTypeFilterQuery(statement, type);

      LocationPage page = new LocationPage();
      page.setType(combinedPage ? null : type);
      page.setLocations(this.graph.query(pageStatement, offset, limit));
      page.setCount(this.graph.getCount(pageStatement));
      page.setLimit(limit);
      page.setOffset(offset);
      page.setStatement(statement);

      if (combinedPage)
      {
        page.setAvailableTypes(this.graph.getTypeCounts(statement));
      }
      else
      {
        this.graph.injectAttributes(page);
      }

      return page;
    }
    catch (Exception e)
    {
      log.error("Error invoking a remote service: ", e);
      log.error("SPARQL statement: " + statement);

      throw new GenericRestException("Unable to map the locations. An error occurred while generating the response", e);
    }
  }
}
