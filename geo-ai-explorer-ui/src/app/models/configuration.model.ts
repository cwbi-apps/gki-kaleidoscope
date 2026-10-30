/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
import { StyleConfig } from "./style.model";
import { VectorLayer } from "./vector-layer.model";

export interface Configuration {
    styles: StyleConfig;
    layers: VectorLayer[];
}

