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
senza create spilo-tutorial.yaml <name> [PARAMETERS]
```

The `<name>` is the same as a senza `<version>` and therefore should adhere to those limitations.
We advise you to use a descriptive name instead of a number, as a data store is supposed to be long lived and the
stack will be upgraded in place. A descriptive name could be `mediawiki` if you are going to use it to store
your own wiki.

Parameters may not be required if you have specified all configuration options in the template.

## Demo Spilo deployment
[![Demo on asciicast](https://asciinema.org/a/32288.png)](https://asciinema.org/a/32288)
