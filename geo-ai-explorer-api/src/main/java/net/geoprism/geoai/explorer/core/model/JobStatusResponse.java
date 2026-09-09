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
package net.geoprism.geoai.explorer.core.model;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Status payload returned by the async job polling endpoints (see
 * {@link net.geoprism.geoai.explorer.core.service.AsyncJobService}).
 *
 * The {@code result} field is only populated once {@code status} is
 * {@code SUCCEEDED}, and holds whatever object the originating request
 * would otherwise have returned synchronously (e.g. a {@code Message} for
 * a chat prompt, or a list of {@code LocationPage} for a location lookup).
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class JobStatusResponse
{
  private String jobId;

  /**
   * One of PENDING, RUNNING, SUCCEEDED, FAILED.
   */
  private String status;

  private Object result;

  private String errorMessage;
}
