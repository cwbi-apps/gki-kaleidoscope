/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
export interface VectorLayer {
    id: string;
    url: string;
    label: string;
    color: string;
    order: number;
    labelProperty: string;
    codeProperty: string;
    prefix: string;
    enabled: boolean;
    sourceLayer: string;
    geometryType: string;
}

