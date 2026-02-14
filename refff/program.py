import os, av
import subprocess
import datetime

def get_length(filename):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    return float(result.stdout)
    
def get_length_dir(dirname):
    length = 0
    print("dirname: ", dirname)

    for dirpath, dirnames, filenames in os.walk(dirname):
        for filename in filenames:
            length = get_length(os.path.join(dirpath, filename)) + length
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
daysNumber = 1

# end_date = start_date + 7*day_delta

for dirpath, dirnames, filenames in os.walk('films'):
    length = 0
    totalLength = 0
    duration = []
    for filename in sorted(filenames):
        # print("Файл:", os.path.join(dirpath, filename))
        # files.append(os.path.join(dirpath, filename))
        fileLength = get_length(os.path.join(dirpath, filename))/60
        while True:
            destination = destinationPath(daysNumber)
            if not os.path.isdir(destination):
                os.makedirs(destination)
                print("Created: ", destination)

            length = get_length_dir(destination)
            # length = 60
            print("length: ", length)
            print("filename: ", filename)
            if length + fileLength <= slot :
                break
            else:
                daysNumber = daysNumber + 1
                print("next")
        # os.replace(os.path.join(dirpath, filename), os.path.join(destination, '0.' + filename))
        daysNumber = daysNumber + 1



        # print("filename:", filename)
        # print("os.path.join(dirpath, filename):", os.path.join(dirpath, filename))
        # print("destination:", destination)


        # names.append(filename)
        # files = tuple(os.path.join(dirpath, filename), filename)
        # print(get_length(os.path.join(dirpath, filename))/60)
        # length = get_length(os.path.join(dirpath, filename))/60
        # duration.append(length)
        # totalLength = totalLength + length
        # totalDuration.append(length)

        # # fh = av.open(os.path.join(dirpath, filename))
        # video = fh.streams.video[0]
        # if (video.duration):
        #     print(float(video.duration * video.time_base/60))
        # else:
        #     print("Файл:", os.path.join(dirpath, filename))
    # if (totalLength):
#         print("Каталог:", dirpath)
#         print("Max:", max(duration))
#         print("Min:", min(duration))
# print("Общая продолжительность:", totalLength)
# print("Max:", max(totalDuration))
# print("Min:", min(totalDuration))
# for file in files:
#     print(file)
"""

for i in range(len(files)+1):
    # print((start_date + i*day_delta).strftime("%d"))
    # print((start_date + i*day_delta).strftime("%m"))
    destination = os.path.join((start_date + i*day_delta).strftime("%m"), (start_date + i*day_delta).strftime("%d"), time)
    if not os.path.isdir(destination):
        os.makedirs(destination)
        print("Created: ", destination)
    # os.replace(files.pop(0), os.path.join(destination, names.pop(0)))
    print(files.pop(0))
    print(names.pop(0))

"""
# print(files.pop(0))
# print(files.pop(0))
# print(files)