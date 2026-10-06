package net.geoprism.geoai.explorer.core.serialization;

import org.locationtech.jts.geom.Geometry;
import org.locationtech.jts.io.geojson.GeoJsonWriter;

import tools.jackson.core.JacksonException;
import tools.jackson.core.JsonGenerator;
import tools.jackson.databind.SerializationContext;
import tools.jackson.databind.ser.std.StdSerializer;

public class GeometrySerializer extends StdSerializer<Geometry>
{
  private static final int DECIMALS = 4;

  public GeometrySerializer()
  {
    super(Geometry.class);
  }

  @Override
  public void serialize(Geometry value, JsonGenerator gen, SerializationContext context) throws JacksonException
  {
    if (value != null)
    {
      GeoJsonWriter writer = new GeoJsonWriter(DECIMALS);
      writer.setEncodeCRS(false);

      gen.writeRawValue(writer.write(value));
    }
  }

}
