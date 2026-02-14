#!/usr/bin/python3
# -*- coding: utf-8 -*-
import os
import subprocess
import datetime

def get_length(filename):
    result = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrapper=s1:nokey=1", filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    return float(result.stdout)
    
def get_length_dir(dirname):
    length = 0
    print("dirname: ", dirname)

    for dirpath, dirnames, filenames in os.walk(dirname):
        for filename in filenames:
            length += get_length(os.path.join(dirpath, filename))
    return length/60
    
def destinationPath(daysNumber):
    day_delta = datetime.timedelta(days=1)
    start_date = datetime.date.today()

    destination = os.path.join((start_date + daysNumber*day_delta).strftime("%m"), (start_date + daysNumber*day_delta).strftime("%d"), time)
    return destination
    
# os.chdir("films")

files = []
# names = []
duration = []
totalDuration = []
time = '9-00'
# максимальная продолжительность слота в минутах
slot = 240
# количество дней, которые необходимо пропустить, включая сегодняшний
daysNumber = 1
# на сколько дней вперед заполняется расписание
daysLimit = 39

# end_date = start_date + 7*day_delta
length = 1

files = []
# for dirpath, dirnames, filenames in os.walk('films.mnt/foreign/branded/'):
for dirpath, dirnames, filenames in os.walk('films'):
    for filename in sorted(filenames):
        fileLength = get_length(os.path.join(dirpath, filename))/60
        files.append(tuple((filename, fileLength, os.path.join(dirpath, filename))))
        print(filename)
        print(dirpath)
        print("File length: ", "%.2f" % fileLength)
        print("---------------")
files.sort(key=lambda i: i[1], reverse=True)
# print(files)
moved = True
while moved:
    if daysNumber > daysLimit:
        print('Расписание сформировано на ' + str(daysLimit) + ' дней вперед.')
        break
    destination = destinationPath(daysNumber)
    print("destination: ", destination)
    if not os.path.isdir(destination):
        os.makedirs(destination)
        print("Created: ", destination)
    length = get_length_dir(destination)
    # if not length:
    #     break
    print("Slot: ", slot)
    print("Need less then:", "%.2f" % (slot - length))
    moved = False
    for file in files[:]:
        if (slot - length) >= file[1]:
            os.replace(file[2], os.path.join(destination, '1.' + file[0]))
            moved = True
            files.remove(file)
            print("Moved: ", file[0], ':', "%.2f" % file[1])
            break
        print("Not moved: ", file[0], ':', "%.2f" % file[1])
        print("daysNumber: ", daysNumber)
        moved = False
        # print(file[0], ':', file[1])
    daysNumber += 1
    print("---------------")
