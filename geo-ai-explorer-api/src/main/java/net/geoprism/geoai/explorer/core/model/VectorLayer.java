/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
package net.geoprism.geoai.explorer.core.model;

import lombok.Data;

@Data
public class VectorLayer
{
  private String  url;

  private String  label;

  private String  color;

  private Integer order;

  private String  labelProperty;

  private String  codeProperty;

  private String  prefix;

  private Boolean enabled;

  private String  sourceLayer;

  private String  geometryType;
}
