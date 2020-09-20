from __future__ import absolute_import, unicode_literals

import octoprint.plugin
import RPi.GPIO as GPIO
import os
import re
import time
import multiprocessing

class AdaptiveFan():
    TEMP_RE = re.compile(r"^temp=(\d+(\.\d+)?)'C$")
    PWM_PERIOD_MS=200
    OFF_DUTY_CYCLE=0
    MIN_POWERED_DUTY_CYCLE=20
    MAX_POWERED_DUTY_CYCLE=100

    def __init__(self, fan_gpio, temperature_config):
        self.fan_gpio = fan_gpio
        self.power=None
        self.temperature_config = temperature_config

    def Start(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.fan_gpio,GPIO.OUT)
        self.fan = GPIO.PWM(self.fan_gpio, self.PWM_PERIOD_MS)
        self.fan.start(0)
        self._SetFan(0)

    def GetTemperature(self):
        try:
            return float(self.TEMP_RE.match(os.popen("vcgencmd measure_temp").readline()).group(1))
        except Exception as e:
            print(e)
            return None

    def GetPower(self):
        return self.power

    def UpdateFan(self):
        temperature = self.GetTemperature()
        if temperature is None:
            print("Failed to get temperature.")
            return
        for temperature_range_config in self.temperature_config:
            min_temperature, max_temperature, min_power, max_power = temperature_range_config
            if (min_temperature is None or temperature >= min_temperature) and (max_temperature is None or temperature < max_temperature):
                scale = (temperature - min_temperature) / (max_temperature - min_temperature)
                fan_power = min_power + scale * (max_power - min_power)
        self._SetFan(fan_power)

    def Stop(self):
        self._SetFan(0)
        GPIO.cleanup()

    def _SetFan(self, power):
        self.power=power
        if power == 0.0:
            duty_cycle = 0.0
        else:
            duty_cycle = self.MIN_POWERED_DUTY_CYCLE + power * (self.MAX_POWERED_DUTY_CYCLE - self.MIN_POWERED_DUTY_CYCLE)
        self.fan.ChangeDutyCycle(duty_cycle)

class PiCpuFanPlugin(octoprint.plugin.StartupPlugin,
                     octoprint.plugin.TemplatePlugin,
                     octoprint.plugin.SettingsPlugin,
                     octoprint.plugin.ShutdownPlugin):
    def on_after_startup(self):
        gpio_pin = int(self._settings.get(['gpio_pin']))
        if gpio_pin == -1:
            print("GPIO Not configured. Giving up.")
            return
        update_period_secs = float(self._settings.get(['update_period_secs']))
        self.fan = AdaptiveFan(gpio_pin, [
            (None, 38.0, 0.0, 0.0),
            (38.0, 45.0, 0.0, 0.7),
            (45.0, 55.0, 0.7, 1.0),
            (55.0, None, 1.0, 1.0),
        ])
        def FanLoop():
            self.fan.Start()
            try:
                while True:
                    self.fan.UpdateFan()
                    print("CPU Temperature is {0}'C. Setting fan power to {1}.".format(self.fan.GetTemperature(), self.fan.GetPower()))
                    time.sleep(update_period_secs)
            except Exception as e:
                print(e)
            finally:
                self.fan.Stop()
        self.fan_thread = multiprocessing.Process(target=FanLoop)
        self.fan_thread.start()

    def on_shutdown(self):
        self.fan_thread.terminate()

    def get_settings_defaults(self):
        return dict(gpio_pin=-1, update_period_secs=10.0)

    def get_template_configs(self):
        return [
            dict(type="settings", custom_bindings=False),
        ]


__plugin_name__ = "Pi Cpu Fan"
__plugin_version__ = "1.0.0"
__plugin_description__ = "Runs a fan on the Raspberry Pi to cool the CPU."
__plugin_pythoncompat__ = ">=2.7,<4"
__plugin_implementation__ = PiCpuFanPlugin()
