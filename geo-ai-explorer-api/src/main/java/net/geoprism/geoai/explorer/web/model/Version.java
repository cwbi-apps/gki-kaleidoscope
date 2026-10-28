package net.geoprism.geoai.explorer.web.model;

import java.time.Instant;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class Version
{
  private String  version;

  private Instant buildTime;

}
