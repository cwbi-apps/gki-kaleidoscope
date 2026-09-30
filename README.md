# Kaleidoscope

Kaleidoscope is a GeoAI application for viewing and exploring authoritative geospatial data in plain language. It uses a Geo-Graph RAG approach: questions are answered from a spatial knowledge graph published by [Geoprism Registry](https://docs.geoprismregistry.com/version/v2.0.0/introduction), rather than from what a language model happens to know.

Kaleidoscope was built for the U.S. Army Corps of Engineers (USACE). Its main use is finding and exploring sites to assess them for flood risk mitigation, and helping produce reports for site analysis and selection. It is intended for planners, emergency managers, water resource managers and analysts who need answers without writing queries or combining GIS layers themselves.

Kaleidoscope was formerly called the GeoAI Explorer, and some modules still use the `geo-ai-explorer` name.

**📖 Documentation: [terraframe.github.io/kaleidoscope-documentation](https://terraframe.github.io/kaleidoscope-documentation/)**

## What you can do with Kaleidoscope

- **Ask questions in plain language**, such as "What built infrastructure is in the study area?"
- **See answers on a map**, with the objects behind each answer shown on the map and in a results table.
- **Explore how places and assets are connected** using the graph visualizer.
- **Inspect the underlying data**, including each object's attributes and its code in Geoprism Registry's knowledge graph.

See the [user guide](https://terraframe.github.io/kaleidoscope-documentation/user-guide/) for details, and [Why Geo-Graph RAG](https://terraframe.github.io/kaleidoscope-documentation/overview/why-geo-graph-rag/) for the approach behind it.

## How it works

Kaleidoscope sits on top of a Geospatial Knowledge Infrastructure (GKI). Geoprism Registry integrates and publishes authoritative data as an RDF knowledge graph. Kaleidoscope's agents turn a user's question into SPARQL queries against that graph, resolve place and asset names through a search index, and return answers that can be traced back to the source records.

The main technologies are:

- **Frontend:** Angular, MapLibre GL and ngx-graph
- **Backend:** Java 17 and Spring Boot
- **AI:** Amazon Bedrock
- **Knowledge graph:** RDF and GeoSPARQL, served by Amazon Neptune (Apache Jena Fuseki for local development)
- **Search:** OpenSearch, used for name resolution

## Repository structure

| Folder | Contents |
| --- | --- |
| `geo-ai-explorer-ui` | Angular web application |
| `geo-ai-explorer-api` | Spring Boot API that connects the UI to the AI agents, knowledge graph and search index |
| `agents` | Instructions and SPARQL prompts for the chat and map agents |
| `lambda` | AWS Lambda functions for SPARQL, schema lookup, name resolution, and Neptune-to-OpenSearch replication |
| `src/build` | Build and packaging configuration, including Fuseki and the web app |
| `doc` | Sample datasets and supporting material |
| `launches` | Eclipse launch configurations |

## Related projects

- [Kaleidoscope documentation](https://terraframe.github.io/kaleidoscope-documentation/)
- [Geoprism Registry](https://github.com/terraframe/geoprism-registry) and its [documentation](https://docs.geoprismregistry.com/version/v2.0.0)

## Contributing

Work is tracked on the [project ticket board](https://github.com/orgs/terraframe/projects/8). Bug reports and feature requests are welcome as [issues](https://github.com/terraframe/kaleidoscope/issues).

## About

Kaleidoscope is developed by [TerraFrame](https://terraframe.com) and funded by the U.S. Army Corps of Engineers.

## License

Kaleidoscope is released under the [MIT License](LICENSE).
