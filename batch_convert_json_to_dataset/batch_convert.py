# Python 3
# Batch convert .json file to dataset folder which contains the label.png file after manually label the area
# Author: Owen Xing
import os 
import glob

try:
    # 1. Change the path to the directory where stores all the .json file
    path_json = input("Please give the path of the directory where stores all the .json file: ") #Owen| path of the directory where stores all the .json file
    os.chdir(path_json)
    print("We are now at", os.getcwd(),", which contains all the .json file that need to be converted to datasets")
    len_json_file = len(glob.glob("*.json"))
    print("And this directory contains total", len(glob.glob("*.json")), ".json file.")

    # 2. Use a for loop to conver each json file to the directory which separately owns the label.png
    for file in glob.glob("*.json"):
        print("----------------------------------------------------", "Converting", file, "----------------------------------------------------")
        command = "labelme_json_to_dataset " + file + " -o " + file[:-5] + "_json"
        os.system(command)

    # 3. Double check the number of the directory which name is xx_json 
    len_json_folder = ([len(folders) for base, folders, files in os.walk(path_json)])[0]
    print("We have converted", len_json_file, "json files into", len_json_folder, "json dataset. The number of json files should equals to the number of json datasets.")
except:
    print("Sorry, it seems that the path is not correct. \nPlease check the path.")