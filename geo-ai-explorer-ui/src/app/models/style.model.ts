/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
export interface Style {
    color: string
    order: number
    label?: string
}

export interface StyleConfig { [key: string]: Style }
