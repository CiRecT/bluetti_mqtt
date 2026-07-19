from pathlib import Path
from typing import List, Literal, Mapping, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
import yaml


DeviceModel = Literal['AC200M', 'AC300', 'AC500', 'AC60', 'EP500', 'EP500P', 'EP600', 'EB3A']
HomeAssistantMode = Literal['normal', 'none', 'advanced']


class ConfigError(ValueError):
    pass


class StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class MQTTConfig(StrictConfigModel):
    host: str = Field(min_length=1)
    port: int = Field(default=1883, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = Field(default=None, repr=False)
    password_env: Optional[str] = None

    @model_validator(mode='after')
    def validate_password_source(self):
        if self.password is not None and self.password_env is not None:
            raise ValueError('password and password_env are mutually exclusive')
        return self


class GridChargingConfig(StrictConfigModel):
    enabled: bool = False
    minimum_update_interval: int = Field(default=10, ge=10)


class DeviceConfig(StrictConfigModel):
    model: DeviceModel
    address: str = Field(min_length=1)
    grid_charging: GridChargingConfig = Field(default_factory=GridChargingConfig)

    @model_validator(mode='after')
    def validate_grid_charging_model(self):
        if self.grid_charging.enabled and self.model != 'AC300':
            raise ValueError('grid_charging can be enabled only for AC300')
        return self


class RuntimeConfig(StrictConfigModel):
    version: Literal[1]
    mqtt: MQTTConfig
    polling_interval: int = Field(default=0, ge=0)
    home_assistant: HomeAssistantMode = 'normal'
    devices: List[DeviceConfig] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_unique_addresses(self):
        addresses = [device.address.casefold() for device in self.devices]
        if len(addresses) != len(set(addresses)):
            raise ValueError('devices must use unique addresses')
        return self


def _format_validation_error(error: ValidationError) -> str:
    messages = []
    for detail in error.errors(include_url=False, include_context=False):
        path = '.'.join(str(part) for part in detail['loc']) or 'configuration'
        messages.append(f'{path}: {detail["msg"]}')
    return '; '.join(messages)


def load_yaml_config(path: Union[str, Path], environ: Mapping[str, str]) -> RuntimeConfig:
    config_path = Path(path)
    try:
        with config_path.open('r', encoding='utf-8') as config_file:
            raw_config = yaml.safe_load(config_file)
    except (OSError, yaml.YAMLError) as error:
        raise ConfigError(f'config: {error}') from error

    try:
        config = RuntimeConfig.model_validate(raw_config)
    except ValidationError as error:
        raise ConfigError(_format_validation_error(error)) from error

    if config.mqtt.password_env is not None:
        password = environ.get(config.mqtt.password_env)
        if password is None:
            raise ConfigError(
                f'mqtt.password_env: environment variable {config.mqtt.password_env!r} is not set'
            )
        mqtt = config.mqtt.model_copy(update={'password': password, 'password_env': None})
        config = config.model_copy(update={'mqtt': mqtt})

    return config
