## Initialize a Spilo template
The configuration for Spilo has a lot of items. To help you build a template for your needs, the `senza` application
has a postgresapp template which will guide you through most of these items.

For more details, check the configuration: [Configuration](/configuration/)

```bash
senza init spilo-tutorial.yaml
```

You should choose the `postgresapp` option in senza.

## Create a Cloud Formation Stack
After this you create a Cloud Formation Stack from the generated template using `senza create`
```bash
senza create spilo-tutorial.yaml <version> [PARAMETERS]
```

Parameters may not be required if you have specified all configuration options in the template.

## Demo Spilo deployment
[![Demo on asciicast](https://asciinema.org/a/32288.png)](https://asciinema.org/a/32288)
