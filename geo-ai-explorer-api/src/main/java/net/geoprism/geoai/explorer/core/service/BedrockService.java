package net.geoprism.geoai.explorer.core.service;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import net.geoprism.geoai.explorer.core.config.AppProperties;
import net.geoprism.geoai.explorer.core.model.GenericRestException;
import net.geoprism.geoai.explorer.core.model.History;
import net.geoprism.geoai.explorer.core.model.Message;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.services.bedrockagentruntime.BedrockAgentRuntimeAsyncClient;
import software.amazon.awssdk.services.bedrockagentruntime.model.InvokeAgentRequest;
import software.amazon.awssdk.services.bedrockagentruntime.model.InvokeAgentResponseHandler;

@Service
public class BedrockService
{
  private static final int MAX_TIMEOUT_MINUTES = 5;

  private static final Logger log = LoggerFactory.getLogger(BedrockService.class);

  private static final Pattern LOCATION_NAME_PATTERN = Pattern.compile(".*<name>(.*?)<\\/name>.*", Pattern.DOTALL);

  @Autowired
  private AppProperties properties;

  public Message prompt(String sessionId, String inputText) throws InterruptedException, ExecutionException, TimeoutException
  {
    String value = invokeAgent(
        properties.getChatAgentId(),
        properties.getChatAgentAliasId(),
        sessionId,
        inputText
    );

    Matcher matcher = LOCATION_NAME_PATTERN.matcher(value);
    boolean find = matcher.find();

    boolean mappable = value.contains("#mapit");
    boolean ambiguous = !mappable &&
        ((find && value.toLowerCase().contains("#ambiguous")) ||
            value.toLowerCase().contains("i found multiple"));

    Message message = new Message();
    message.setContent(
        value
            .replace("#mapit", "")
            .replace("#ambiguous", "")
            .replaceFirst("<name>(.*?)<\\/name>", "")
    );
    message.setSessionId(sessionId);
    message.setMappable(mappable);
    message.setAmbiguous(ambiguous);

    if (find)
    {
      message.setLocation(matcher.group(1));
    }

    return message;
  }

  public String getLocationSparql(History history)
      throws InterruptedException, ExecutionException, TimeoutException
  {
    String text = history.toText();

    log.info("Invoking SPARQL agent {} with text: {}", properties.getSparqlAgentAliasId(), text);

    String response = invokeAgent(
        properties.getSparqlAgentId(),
        properties.getSparqlAgentAliasId(),
        UUID.randomUUID().toString(),
        text
    );
    
    // No idea why bedrock is redacting the word 'sparl'? Could be because its a tool parameter I don't know.
    response = response.replaceAll("<REDACTED>", "sparql");

    return stripCodeFence(response);
  }

  private String invokeAgent(String agentId, String agentAliasId, String sessionId, String inputText)
      throws InterruptedException, ExecutionException, TimeoutException
  {
    validateAgentConfiguration(agentId, agentAliasId);

    final StringBuilder content = new StringBuilder();

    try (BedrockAgentRuntimeAsyncClient client = getClient())
    {
      InvokeAgentRequest request = InvokeAgentRequest.builder()
          .agentId(agentId)
          .agentAliasId(agentAliasId)
          .sessionId(sessionId)
          .inputText(inputText)
          .enableTrace(false)
          .build();

      InvokeAgentResponseHandler handler = InvokeAgentResponseHandler.builder()
          .onResponse(response -> {
            log.info("Response received from Bedrock agent: {}", response);
          })
          .onEventStream(publisher -> {
            publisher.subscribe(event -> {
              log.info("Event: {}", event);

              event.accept(InvokeAgentResponseHandler.Visitor.builder()
                  .onChunk(payload -> content.append(payload.bytes().asUtf8String()))
                  .build());
            });
          })
          .onError(error -> {
            log.error("Error occurred while invoking Bedrock agent", error);
          })
          .build();

      CompletableFuture<Void> future = client.invokeAgent(request, handler);

      future.get(MAX_TIMEOUT_MINUTES, TimeUnit.MINUTES);
    }

    return content.toString();
  }

  private void validateAgentConfiguration(String agentId, String agentAliasId)
  {
    if (agentId == null || agentId.isBlank() || agentAliasId == null || agentAliasId.isBlank())
    {
      throw new GenericRestException("Bedrock agent id and alias id must be configured before invoking Bedrock.");
    }
  }

  private String stripCodeFence(String response)
  {
    String text = response.trim();

    if (text.startsWith("```"))
    {
      text = text.replaceFirst("^```(?:sparql|sql)?\\s*", "");
      text = text.replaceFirst("\\s*```$", "");
      text = text.trim();
    }

    return text;
  }

  private BedrockAgentRuntimeAsyncClient getClient()
  {
    final Duration sdkTimeout = Duration.ofMinutes(MAX_TIMEOUT_MINUTES);
    final Duration nettyReadTimeout = Duration.ofMinutes(MAX_TIMEOUT_MINUTES);

    return BedrockAgentRuntimeAsyncClient.builder()
        .region(properties.getBedrockRegion())
        .credentialsProvider(properties.getCredentialsProvider())
        .httpClientBuilder(
            NettyNioAsyncHttpClient.builder()
                .readTimeout(nettyReadTimeout)
        )
        .overrideConfiguration(cfg -> {
          cfg.apiCallTimeout(sdkTimeout);
          cfg.apiCallAttemptTimeout(sdkTimeout);
        })
        .build();
  }
}
