# Diagram sources

Each `*.workflow.json` here is the source of the diagram of the same name one folder up. To rebuild one, run this from the Archify skill folder:

    node bin/archify.mjs deliver workflow <repo>/docs/guide/diagrams/src/<name>.workflow.json <repo>/docs/guide/diagrams/<name>.html --quality showcase

Copy only the `.html` into `docs/guide/diagrams/`. This folder is excluded from the published site.
