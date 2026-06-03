package net.geoprism.geoai.explorer.core.model;

import java.util.LinkedList;
import java.util.List;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class PageRequest
{
  private String         statement;
  
  private String         type;

  private int            offset = 0;

  private int            limit  = 1000;

  private List<String>   excludedTypes = new LinkedList<>();
  
  private String         sortField;
  
  private String         sortDirection;
}
