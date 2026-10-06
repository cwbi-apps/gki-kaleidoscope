package net.geoprism.geoai.explorer.core.model;

import java.util.LinkedList;
import java.util.List;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import lombok.Data;

@Data
public class History
{
  private List<HistoryMessage> messages = new LinkedList<>();

  private int                  limit    = 1000;

  private int                  offset   = 0;

  public void addMessage(HistoryMessage message)
  {
    this.messages.add(message);
  }

  public String toText()
  {
    ObjectMapper mapper = new ObjectMapper();

    try
    {
      return mapper.writeValueAsString(this);
    }
    catch (JacksonException e)
    {
      throw new RuntimeException(e);
    }
  }

}
