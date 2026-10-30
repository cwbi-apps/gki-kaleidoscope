/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
package net.geoprism.geoai.explorer.core.model;

import java.util.HashMap;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;

import lombok.Data;

@Data
public class Graph
{
	private Map<String, Integer> typeCount = new HashMap<String, Integer>();
	
	private List<Location> nodes = new LinkedList<Location>();

	private List<Edge>     edges = new LinkedList<Edge>();
}
