#!/usr/bin/python3
# -*- coding: utf-8 -*-
import os
import subprocess
import datetime

def isSunday(daysNumber):
    day_delta = datetime.timedelta(days=1)
    start_date = datetime.date.today()
    weekday = (start_date + daysNumber*day_delta).strftime("%w")
    # print("weekday: ", weekday)
    # print("weekday: ", type(weekday))
    if weekday == "0":
        # print("weekday: ", weekday)
        return True
    return False

def destinationPath(daysNumber):
    day_delta = datetime.timedelta(days=1)
    start_date = datetime.date.today()

    destination = os.path.join((start_date + daysNumber*day_delta).strftime("%m"), (start_date + daysNumber*day_delta).strftime("%d"), time)
    return destination

for daysNumber in range(300):
    time = '6-00'
    # if isSunday(daysNumber):
    #     time = '7-00'
    destination = destinationPath(daysNumber)
    if not os.path.isdir(destination):
        os.makedirs(destination)
        print("Created: ", destination)

for daysNumber in range(300):
    time = '9-00'
    # if isSunday(daysNumber):
    #     time = '7-00'
    destination = destinationPath(daysNumber)
    if not os.path.isdir(destination):
        os.makedirs(destination)
        print("Created: ", destination)

for daysNumber in range(300):
    time = '14-30'
    # if isSunday(daysNumber):
    #     time = '7-00'
    destination = destinationPath(daysNumber)
    if not os.path.isdir(destination):
        os.makedirs(destination)
        print("Created: ", destination)

for daysNumber in range(300):
    time = '19-00'
    # if isSunday(daysNumber):
    #     time = '7-00'
    destination = destinationPath(daysNumber)
    if not os.path.isdir(destination):
        os.makedirs(destination)
        print("Created: ", destination)