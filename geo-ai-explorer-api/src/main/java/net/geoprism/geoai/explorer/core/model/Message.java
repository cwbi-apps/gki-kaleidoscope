/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
package net.geoprism.geoai.explorer.core.model;

import lombok.Data;

@Data
public class Message
{
  /**
   * Content of the message
   */
  private String  content;
  
  private String reasoning;

  /**
   * Session if of the conversation
   */
  private String  sessionId;

  /**
   * Flag indicating if the message represents a mappable message
   */
  private Boolean mappable;

  private Boolean ambiguous;

  private String  location;

}
