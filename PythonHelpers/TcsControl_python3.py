#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=== Authors ===
Dr. Ulrike Horn: uhorn@cbs.mpg.de
Max Planck Institute for Human Cognitive and Brain Sciences
Research group Pain Perception
Date: 26th May 2021
"""

import serial


class TcsDevice:
    def __init__(self, port='/dev/ttyACM0'):
        # some initial parameters
        self.baseline = 30.0
        # Open serial port
        self.s_port = serial.Serial(port, 115200, timeout = 2)
        self.s_port.flushInput();
        self.s_port.write(bytes(b'H'))
        self.s_port.flushOutput()
        firmware_msg = self.s_port.read(30)
        print(firmware_msg)
        self.s_port.flushInput()
        id_msg = self.s_port.read(30)
        print(id_msg)
        self.s_port.flushInput()
        # read the rest
        rest = self.s_port.read(10000)
        self.s_port.flushInput()

    def set_quiet(self):
        """
        sets thermode to quiet mode
        otherwise TCS sends regularly temperature data
        (@1Hz if no stimulation, @100Hz during stimulation)
        and that can corrupt dialog between PC and TCS
        """
        self.s_port.write(bytes(b'F'))
        self.s_port.flushOutput()
    
    
    def set_baseline(self, baselineTemp):
        """
        sets baseline temperature in °C (also called neutral temperature)
        :param baselineTemp: 1 float value (min 20°C, max 40°C)
        """
        if baselineTemp > 40:
            baselineTemp = 40
        if baselineTemp < 20:
            baselineTemp = 20   
        command = b'N%03d' % (baselineTemp*10)
        self.s_port.write(bytes(command))
        self.s_port.flushOutput()
    
    
    def set_durations(self, stimDurations):
        """
        sets stimulus durations in s for all 5 zones
        :param stimDurations: array of 5 values (min 0.001s, max 99.999s)
        """
        for i in range(5):
            if stimDurations[i] > 99.999:
                stimDurations[i] = 99.999
            if stimDurations[i] < 0.001:
                stimDurations[i] = 0.001
        # check if speeds are equal
        if stimDurations.count(stimDurations[0]) == len(stimDurations):
            # yes: send all speeds in one command
            command = b'D0%05d' % (stimDurations[1]*1000)
            self.s_port.write(bytes(command))
            self.s_port.flushOutput()
        else:       
            # no: send speeds in separate commands
            for i in range(5):
                command = b'D%d%05d' % ((i+1) , (stimDurations[i]*1000))
                self.s_port.write(bytes(command))
                self.s_port.flushOutput()
    
    
    def set_ramp_speed(self, rampSpeeds):
        """
        sets ramp up speeds in °C/s for all 5 zones
        :param rampSpeeds: array of 5 values (min 0.1°C/s, max 300°C/s)
        """
        for i in range(5):
            if rampSpeeds[i] > 300:
                rampSpeeds[i] = 300
            if rampSpeeds[i] < 0.1:
                rampSpeeds[i] = 0.1
        
        # check if speeds are equal
        if rampSpeeds.count(rampSpeeds[0]) == len(rampSpeeds):
            # yes: send all speeds in one command
            command = b'V0%04d' % (rampSpeeds[1]*10)
            self.s_port.write(bytes(command))
            self.s_port.flushOutput()
        else:        
            # no: send speeds in separate commands
            for i in range(5):
                command = b'V%d%04d' % ((i+1), (rampSpeeds[i]*10))
                self.s_port.write(bytes(command))
                self.s_port.flushOutput()
    
    def set_return_speed(self, returnSpeeds):
        """
        sets ramp down/ return speeds in °C/s for all 5 zones
        :param returnSpeeds: array of 5 values (min 0.1°C/s, max 300°C/s)
        """
        for i in range(5):
            if returnSpeeds[i] > 300:
                returnSpeeds[i] = 300
            if returnSpeeds[i] < 0.1:
                returnSpeeds[i] = 0.1
        
        # check if speeds are equal
        if returnSpeeds.count(returnSpeeds[0]) == len(returnSpeeds):
            # yes: send all speeds in one command
            command = b'R0%04d' % (returnSpeeds[1]*10)
            self.s_port.write(bytes(command))
            self.s_port.flushOutput()
        else:        
            # no: send speeds in separate commands
            for i in range(5):
                command = b'R%d%04d' % ((i+1), (returnSpeeds[i]*10))
                self.s_port.write(bytes(command))
                self.s_port.flushOutput()
    
    
    def set_temperatures(self, temperatures):
        """
        sets target temperatures in °C for all 5 zones
        :param temperatures: array of 5 values (min 0.1°C, max 60°C)
        """
        for i in range(5):
            if temperatures[i] > 60:
                temperatures[i] = 60
            if temperatures[i] < 0.1:
                temperatures[i] = 0.1
        
        # check if temperatures are equal
        if temperatures.count(temperatures[0]) == len(temperatures):
            # yes: send all speeds in one command
            command = b'C0%03d' % (temperatures[1]*10)
            self.s_port.write(bytes(command))
            self.s_port.flushOutput()
        else:        
            # no: send speeds in separate commands
            for i in range(5):
                command = b'C%d%03d' % ((i+1), (temperatures[i]*10))
                self.s_port.write(bytes(command))
                self.s_port.flushOutput()
    
    
    def set_follow(self):
        """
        enters follow mode (Od command): the TCS continuously ramps toward
        the last target temperatures sent via set_temperatures().
        """
        self.s_port.write(bytes(b'Od'))
        self.s_port.flushOutput()

    def abort_stimulation(self):
        """
        force halt to current stimulation (A command).
        """
        self.s_port.write(bytes(b'A'))
        self.s_port.flushOutput()

    def stimulate(self):
        """
        starts the stimulation protocol with the parameters that have been set
        """
        self.s_port.write(bytes(b'L'))



    def get_temperatures(self):
        """
        get current temperatures of zone 1 to 5 in °C
        :return: returns an array of five temperatures or empty array if 
            there is an error
        """
        self.s_port.flushInput()
        self.s_port.write(bytes(b'E'))
        self.s_port.flushOutput()
        # '/r' + 'xxx?xxx?xxx?xxx?xxx?xxx' with '?' = sign '+' ou '-'
        # neutral + t1 to t5
        data = self.s_port.read(24)
        temperatures = [0, 0, 0, 0, 0]
        if len(data) > 23:
            neutral = float(data[2:4]);
            temperatures[0] = float(data[5:8]) / 10;
            temperatures[1] = float(data[9:12]) / 10;
            temperatures[2] = float(data[13:16]) / 10;
            temperatures[3] = float(data[17:20]) / 10;
            temperatures[4] = float(data[21:24]) / 10;
        else:
            temperatures = []
        return temperatures
    
    
    def close(self):
        self.s_port.close()
    
    
    