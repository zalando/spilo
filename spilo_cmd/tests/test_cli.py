import collections

from click.testing import CliRunner

from spilo.spilo import cli, process_options, print_spilos, tunnel

Spilo = collections.namedtuple('Spilo', 'stack_name, version, dns, elb, instances, vpc_id, stack')


def test_cli():
    cli


def test_tunnel():
    arguments = []
    runner = CliRunner()
    result = runner.invoke(tunnel, arguments)
    assert 'Usage: tunnel [OPTIONS] CLUSTER' in result.output

    arguments = ['--list', True, 'abc']
    result = runner.invoke(tunnel, arguments)
    assert result.output == ''

    options = ['--pg_service-file', 'tests/pg_service.conf', 'mock']
    result = runner.invoke(tunnel, options)
    assert result.exit_code == -1
    assert 't3st' in str(result.exception)

    arguments = ['abc']
    result = runner.invoke(tunnel, arguments)
    assert result.exit_code != 0


def test_list():
    pass


def test_option_processing():
    process_options(opts=None)
    process_options(opts={'loglevel': 'DEBUG', 'cluster': 'feike', 'odd_config_file': '~/.config/piu/piu.yaml'})


def test_print_spilos():
    spilos = list()
    print_spilos(spilos)

    spilos.append(Spilo(None, None, None, None, None, None, None))
    print_spilos(spilos)

    spilos.append(Spilo(None, None, None, None, None, None, None))
    print_spilos(spilos)
