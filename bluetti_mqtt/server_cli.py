import argparse
import asyncio
import logging
import os
import signal
from typing import Mapping, Optional
import warnings
import sys
from bluetti_mqtt.bluetooth import scan_devices
from bluetti_mqtt.bus import EventBus
from bluetti_mqtt.config import ConfigError, RuntimeConfig, load_yaml_config
from bluetti_mqtt.device_handler import DeviceHandler
from bluetti_mqtt.mqtt_client import MQTTClient


class CommandLineHandler:
    def __init__(self, argv=None, environ: Optional[Mapping[str, str]] = None):
        self.argv = list(sys.argv if argv is None else argv)
        self.environ = os.environ if environ is None else environ

    def _build_parser(self):
        parser = argparse.ArgumentParser(
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description='Scans for Bluetti devices and logs information')
        parser.add_argument(
            '--config',
            metavar='PATH',
            help='Load all runtime configuration from a versioned YAML file')
        parser.add_argument(
            '--scan',
            action='store_true',
            help='Scans for devices and prints out addresses')
        parser.add_argument(
            '--broker',
            metavar='HOST',
            dest='hostname',
            help='The MQTT broker host to connect to')
        parser.add_argument(
            '--port',
            default=1883,
            type=int,
            help='The MQTT broker port to connect to - defaults to %(default)s')
        parser.add_argument(
            '--username',
            type=str,
            help='The optional MQTT broker username')
        parser.add_argument(
            '--password',
            type=str,
            help='The optional MQTT broker password')
        parser.add_argument(
            '--interval',
            default=0,
            type=int,
            help='The polling interval - default is to poll as fast as possible')
        parser.add_argument(
            '--ha-config',
            default='normal',
            choices=['normal', 'none', 'advanced'],
            help='What fields to configure in Home Assistant - defaults to most fields ("normal")')
        parser.add_argument(
            'addresses',
            metavar='ADDRESS',
            nargs='*',
            help='The device MAC(s) to connect to')
        return parser

    def parse(self):
        parser = self._build_parser()
        raw_args = self.argv[1:]
        config_requested = any(arg == '--config' or arg.startswith('--config=') for arg in raw_args)

        if config_requested:
            config_only = (
                (len(raw_args) == 2 and raw_args[0] == '--config')
                or (len(raw_args) == 1 and raw_args[0].startswith('--config='))
            )
            if not config_only:
                raise ConfigError('--config cannot be combined with CLI runtime arguments')
            args = parser.parse_args(raw_args)
            return load_yaml_config(args.config, self.environ)

        return parser.parse_args(raw_args)

    def execute(self):
        parser = self._build_parser()
        try:
            args = self.parse()
        except ConfigError as error:
            parser.error(str(error))

        # The default event loop on windows doesn't support add_reader, which
        # is required by aiomqtt
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        if isinstance(args, RuntimeConfig):
            self.start(args)
        elif args.scan:
            asyncio.run(scan_devices())
        elif args.hostname and len(args.addresses) > 0:
            self.start(args)
        else:
            parser.print_help()

    def start(self, args: argparse.Namespace):
        loop = asyncio.get_event_loop()

        # Register signal handlers for safe shutdown
        if sys.platform != 'win32':
            signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
            for s in signals:
                loop.add_signal_handler(s, lambda: asyncio.create_task(shutdown(loop)))

        # Register a global exception handler so we don't hang
        loop.set_exception_handler(handle_global_exception)

        try:
            loop.create_task(self.run(args))
            loop.run_forever()
        finally:
            loop.close()
            logging.debug("Shut down completed")

    async def run(self, args):
        loop = asyncio.get_running_loop()
        bus = EventBus()

        if isinstance(args, RuntimeConfig):
            hostname = args.mqtt.host
            port = args.mqtt.port
            username = args.mqtt.username
            password = args.mqtt.password
            home_assistant_mode = args.home_assistant
            interval = args.polling_interval
            addresses = [device.address for device in args.devices]
            expected_models = {device.address: device.model for device in args.devices}
            grid_charging_addresses = {
                device.address for device in args.devices if device.grid_charging.enabled
            }
            minimum_update_intervals = {
                (device.address, 'grid_charging_current_limit'): device.grid_charging.minimum_update_interval
                for device in args.devices
                if device.grid_charging.enabled
            }
        else:
            hostname = args.hostname
            port = args.port
            username = args.username
            password = args.password
            home_assistant_mode = args.ha_config
            interval = args.interval
            addresses = list(set(args.addresses))
            expected_models = None
            grid_charging_addresses = set()
            minimum_update_intervals = None

        # Set up strong reference for tasks
        self.background_tasks = set()

        # Start event bus
        bus_task = loop.create_task(bus.run())
        self.background_tasks.add(bus_task)
        bus_task.add_done_callback(self.background_tasks.discard)

        # Start MQTT client
        mqtt_client = MQTTClient(
            bus=bus,
            hostname=hostname,
            home_assistant_mode=home_assistant_mode,
            port=port,
            username=username,
            password=password,
            grid_charging_addresses=grid_charging_addresses,
        )
        mqtt_task = loop.create_task(mqtt_client.run())
        self.background_tasks.add(mqtt_task)
        mqtt_task.add_done_callback(self.background_tasks.discard)

        # Start bluetooth handler (manages connections)
        handler = DeviceHandler(
            addresses,
            interval,
            bus,
            expected_models=expected_models,
            minimum_update_intervals=minimum_update_intervals,
        )
        bluetooth_task = loop.create_task(handler.run())
        self.background_tasks.add(bluetooth_task)
        bluetooth_task.add_done_callback(self.background_tasks.discard)


def handle_global_exception(loop, context):
    if 'exception' in context:
        logging.error('Crashing with uncaught exception:', exc_info=context['exception'])
    else:
        logging.error(f'Crashing with uncaught exception: {context["message"]}')
    asyncio.create_task(shutdown(loop))


async def shutdown(loop: asyncio.AbstractEventLoop):
    logging.info('Shutting down...')
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()


def main(argv=None):
    debug = os.environ.get('DEBUG')
    level = logging.INFO
    if debug:
        level = logging.DEBUG
        warnings.simplefilter('always')

    logging.basicConfig(
        datefmt='%Y-%m-%d %H:%M:%S',
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=level
    )

    cli = CommandLineHandler(argv)
    cli.execute()


if __name__ == "__main__":
    main(sys.argv)
