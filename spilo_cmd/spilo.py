import click
import atexit
import getpass
import logging
import re
import sys
import os
import prettytable
import json
import time
import socket
import subprocess
import yaml
import configparser

from clickclick import AliasedGroup, OutputFormat

processed = False
PIUCONFIG = '~/.config/piu/piu.yaml'
if sys.platform == 'darwin':
    PIUCONFIG = '~/Library/Application Support/piu/piu.yaml'
PIUCONFIG = os.path.expanduser(PIUCONFIG)

option_port      = click.option('-p','--port', type=click.INT, help='The PostgreSQL port', envvar='PGPORT', default=5432)
option_log_level = click.option('--log-level', '--loglevel', help='Set the log level.', default='WARNING')
option_odd_host  = click.option('--odd-host',         help='Odd SSH bastion hostname')
option_odd_user  = click.option('--odd-user',         help='Username to use for OAuth2 authentication')
option_odd_config_file = click.option('--odd-config-file',  help='Alternative odd config file', type=click.Path(exists=False), default=os.path.expanduser(PIUCONFIG))
option_pg_service_file = click.option('--pg_service-file',  help='The PostgreSQL service file', envvar='PGSERVICEFILE', type=click.Path(exists=True))

cluster_argument = click.argument('cluster')



@click.group(cls=AliasedGroup)
def cli():
    """
    Spilo can connect to your Spilo cluster running inside a vpc. It does this using the stups infrastructure.
    """
    global processes
    global tunnels
    global options
    
    processes    = dict()
    tunnels      = dict()

    ## Ensure all are spawned processes will be cleaned in the end
    atexit.register(cleanup)

#    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=options['loglevel'])

def process_options(opts):
    global options
    global odd_config
    global pg_service_name
    global pg_service
    global odd_config
    global processed

    if processed:
        logging.debug('We have already processed options')
        return

    processed = True

    options = opts 

    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=options['loglevel'])   
    pg_service_name, pg_service = get_pg_service()
    odd_config = load_odd_config()

def cleanup():
    for name in processes:
        if processes[name].returncode is None:
            logging.info("Terminating process {} (pid={})".format(name, processes[name].pid))
            processes[name].kill()
    os.system('stty sane')

def libpq_parameters():
    parameters = dict()
    parameters['host'] = 'localhost'
    parameters['port'] = tunnels['postgres']

    if pg_service_name is not None:
        parameters['service'] = pg_service_name

    return parameters, ' '.join(['{}={}'.format(k, v) for k, v in parameters.items()])

@cli.command('connect', short_help='Connect using psql')
@cluster_argument
@option_port
@option_pg_service_file
@option_odd_config_file
@option_odd_user
@option_odd_host
@option_log_level
@click.argument('psql_arguments', nargs=-1, metavar='[-- [psql OPTIONS]]')
def connect(**options):
    """Connects to the the cluster specified using psql"""

    process_options(options)

    tunnel_pid = open_tunnel()
    
    psql_cmd = ['psql', libpq_parameters()[1]]
    psql_cmd.extend(options['psql_arguments'])
    
    logging.debug('psql command: {}'.format(psql_cmd))
   
    psql = subprocess.Popen(psql_cmd)
    processes['psql'] = psql
    psql.wait()

@cli.command('healthcheck', short_help='Healthcheck')
@click.option('--watch', help='Keep watching every WATCH seconds')
@option_port
@option_pg_service_file
@cluster_argument
@click.argument('libpq_parameters', nargs=-1)
def healthcheck(**options):
    """Does a healthcheck on the given cluster"""
    pass

@cli.command('list', short_help='List something')
@option_log_level
@click.argument('clusters', nargs=-1)
def _list(**options):
    process_options(options)

    list_tunnels(options['clusters'])

def list_tunnels(cluster_names=None):
    logging.debug('Cluster names: {}'.format(cluster_names))

    processes = get_my_processes(cluster_names)
    processes.sort(key=lambda k: k['cluster'])

    if len(processes) == 0:
        return

    columns = ['pid','process','cluster','pgport','patroniport','dsn']
    table = prettytable.PrettyTable(columns)
    table.align['cluster'] = 'r'
    table.align['pid'] = 'r'
    table.align['pgport'] = 'r'
    table.align['patroniport'] = 'r'
    for p in processes:
        table.add_row([p[c] for c in columns])

    print(table)

def get_my_processes(cluster_names=None):
    if isinstance(cluster_names, str):
        cluster_names = [cluster_names]

    logging.debug("Cluster names: {}".format(cluster_names))

    """List all the processes that are run by this user and are managed by us"""
    ## We do not use psutil for processes, as environment variables of processes is not 
    ## available from it. We will just use good old ps for the task

    ps_cmd = ['ps','e','-eww','-u',getpass.getuser(),'-A','-o','pid,command']  
 
    ps_output = subprocess.check_output(ps_cmd, shell=False, stderr=subprocess.DEVNULL, env={'LANG':'C'}).splitlines()
    ps_output.reverse()

    logging.debug("Examining {} processes".format(len(ps_output)))

    processes = list()

    process_re     = re.compile('^\s*(\d+)\s+([^\s]+).*SPILOCLUSTER=([^\s]+)')
    pgport_re      = re.compile('SPILOPGPORT=(\d+)')
    patroniport_re = re.compile('SPILOPATRONIPORT=(\d+)')
    service_re     = re.compile('SPILOSERVICE=(\w+)')

    ## We cannot disable the header on every ps (Mac OS X for example), the first line is a header)
    line = ps_output.pop().decode("utf-8")
    while len(ps_output) > 0:
        line = ps_output.pop().decode("utf-8")
        
        match = process_re.search(line)
        if match:
            logging.debug("Matched line: {}".format(line[0:120]))
            process = dict()
            process['pid']     = match.group(1)
            process['process'] = match.group(2)
            process['cluster'] = match.group(3)

            match = process_re.match(line)
            
            process['pid'] = match.group(1)
            process['process'] = match.group(2)
           

            match = pgport_re.search(line)
            if match:
                process['pgport'] = match.group(1)

            match = patroniport_re.search(line)
            if match:
                process['patroniport'] = match.group(1)
            
            match = service_re.search(line)
            if match:
                process['service'] = match.group(1)

            logging.debug("Process: {}".format(process))        
            if cluster_names is None or len(cluster_names) == 0 or any(process['cluster'].startswith(cn) for cn in cluster_names):
                processes.append(process)

        else:
            logging.debug("Disregarding line: {}".format(line))

    for p in processes:
        p['dsn'] = '"host=localhost port={} service={}"'.format(p['pgport'], p['service'])

    logging.debug('Processes : {}'.format(pretty(processes)))
    return processes


@cli.command('tunnel', short_help='Create a tunnel')
@click.option('--background/--no-background', default=True, help='Push the tunnel in the background')
@cluster_argument
@option_port
@option_pg_service_file
@option_odd_config_file
@option_odd_user
@option_odd_host
@option_log_level
def tunnel(**options):
    """Sets up a tunnel to use for connecting to Spilo"""
    global tunnels

    process_options(options)
    
    tunnel_pid = open_tunnel()

    if pg_service_name is None:
        pg_service_env = ''
    else:
        pg_service_env = 'export PGSERVICE={}'.format(pg_service_name)


    print("""
The ssh tunnel is running as a process with pid {pid}.

You can now connect to {cluster} using the following information:

"{dsn}"

Examples:

    psql "{dsn}"
    pg_dump "{dsn}"
    pg_basebackup -d "{dsn}" --pgdata=- --format=tar | gzip -4 > "{cluster}-backup.tar.gz"

Or you can set the environment so you connect using your chosen tool:

export PGHOST=localhost
export PGPORT={port}
{pgservice}

""".format(pid=tunnel_pid, cluster=options['cluster'], dsn=libpq_parameters()[1], port=tunnels['postgres'], pgservice=pg_service_env))
    
    list_tunnels(options['cluster'])
    
    sys.exit(0)

   


def pretty(something):
    return json.dumps(something, sort_keys=True, indent=4)

def get_pg_service():
    """Reads all the services from all the pg service files it can find"""

    ## http://www.postgresql.org/docs/current/static/libpq-pgservice.html
    ##
    ## There are some precedence rules which we want to honour.

    if options.get('cluster') is None:
        return None, dict()
   
    filenames = list()

    if options['pg_service_file'] is not None:
        filenames.append(options['pg_service_file'])
    else:
        filenames.append('~/.pg_service.conf') 
        filenames.append('~/pg_service.conf')
        if filenames.append(os.environ.get('PGSYSCONFDIR')) is not None:
            filenames.append(os.environ.get('PGSYSCONFDIR')+'/pg_service.conf')
        filenames.append('/etc/pg_service.conf')

    filenames = [os.path.expanduser(f) for f in filenames if f is not None]

    logging.debug(pretty(options))

    defaults = dict()
    defaults['port'] = options['port']
    defaults['host'] = options['cluster']

    parser = configparser.ConfigParser(defaults=defaults)

    services = [options['cluster'], 'spilo']
    parsed = parser.read(filenames)
    logging.debug("Read pg_service definitions from the following files: {}".format(parsed))

    pg_service = dict()

    for service in services:
        if parser.has_section(service):
            logging.debug('Using service definition [{}]'.format(service))
            return service, dict(parser.items(service, raw=True))
    
    return None, dict(parser.items('DEFAULT', raw=True))


def load_odd_config():
    if options.get('odd_config_file') is None:
        return dict()

    if os.path.isfile(options['odd_config_file']):
        with open(options['odd_config_file'], 'r') as f:
            odd_config = yaml.load(f)
        logging.debug("Loaded odd configuration from {}:\n{}".format(options['odd_config_file'], pretty(odd_config)))
    else:
        odd_config = dict()

    odd_config['user_name'] = options.get('odd_user') or odd_config.get('user_name')
    odd_config['odd_host'] = options.get('odd_host') or odd_config.get('odd_host')

    return odd_config

def open_tunnel():
    p = get_my_processes(cluster_names=options['cluster'])
    if len(p) > 0:
        logging.info("Found a tunnel which is available: {}".format(pretty(p)))
        tunnels['postgres'] = p[0]['pgport']
        tunnels['patroni']  = p[0]['patroniport']
        return p[0]['pid']

    logging.info("Didn't find a tunnel available")
    ## We open 2 sockets and let the OS pick a free port for us
    ## later on we will use these ports for portforwarding
    pg_socket = socket.socket()
    pg_socket.bind(('', 0))
    tunnels['postgres'] = int(pg_socket.getsockname()[1])
    logging.debug("Postgres tunnel port: {}".format(tunnels['postgres']))
    
    patroni_socket = socket.socket()
    patroni_socket.bind(('', 0))
    tunnels['patroni'] = int(patroni_socket.getsockname()[1])
    logging.debug("tunnel port: {}".format(tunnels['postgres']))

    ssh_cmd = ['ssh']
    if odd_config['user_name'] is not None:
        ssh_cmd += ['{}@{}'.format(odd_config['user_name'], odd_config['odd_host'])]
    else:
        ssh_cmd += [odd_config['odd_host']]

    logging.debug('Testing ssh access using cmd:{}'.format(ssh_cmd))
    test = subprocess.check_output(ssh_cmd + ['printf t3st'], shell=False, stderr=subprocess.DEVNULL)
    if test != b't3st':
        logging.error('Could not setup a working tunnel. You may need to request access using piu')
        raise Exception(str(test))
    
    env = os.environ.copy()
    env['SPILOCLUSTER'] = options['cluster']
    env['SPILOSERVICE'] = pg_service_name

    # # We will close the opened socket as late as possible, to prevent other processes from occupying this port
    patroni_socket.close()
    pg_socket.close()
    
    ssh_cmd.append('-L')
    logging.debug(pg_service)
    
    env['SPILOPGPORT'] = str(tunnels['postgres'])
    port = str(pg_service['port'] or options['port'])
    ssh_cmd.append('{}:{}:{}'.format(tunnels['postgres'], pg_service['host'], str(port)))
    
    ssh_cmd.append('-L')
    env['SPILOPATRONIPORT'] = str(tunnels['patroni'])
    port = 8008
    ssh_cmd.append('{}:{}:{}'.format(tunnels['patroni'], pg_service['host'], str(port)))

    ssh_cmd.append('-N')

    logging.info('Setting up tunnel command: {}'.format(ssh_cmd))

    tunnel = subprocess.Popen(ssh_cmd, shell=False, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, env=env)
    tunnel.poll()
    if tunnel.returncode is not None:
        raise Exception('Tunnel not running anymore, exitcode tunnel: {}'.format(tunnel.returncode))

    # # Wait for the tunnel to be available
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    conn_test = '127.0.0.1', tunnels['postgres']
    result = sock.connect_ex(conn_test)

    timeout = 5
    epoch_time = time.time()
    threshold_time = time.time() + timeout

    # # Loop until connection is established
    while result != 0:
        time.sleep(0.1)
        result = sock.connect_ex(conn_test)
        if time.time() > threshold_time:
            raise Exception('Tunnel was not established within timeout of {} seconds'.format(timeout))
            break

    sock.close()

    logging.debug('Established connectivity on tunnel after {} seconds'.format(time.time() - epoch_time))

    if not options['background']:
        processes['tunnel'] = tunnel
    
    return tunnel.pid

if __name__ == '__main__':
    cli()
