import os 
import random
import glob
import json 
from shutil import copyfile
import argparse


ap = argparse.ArgumentParser()
ap.add_argument("-d", "--main_dir", required=True,
	help="path to dataset")
args = vars(ap.parse_args())

main_dir = args['main_dir']
string =' '
temp = main_dir.split('/')[:-1]
cwd  = string.join(temp).replace(' ','/')


test_percentage = 0.3
os.chdir(main_dir)
list_of_images = glob.glob('*.jpg')

random.seed(4)
random.shuffle(list_of_images)

list_of_test  = list_of_images[:round(test_percentage*len(list_of_images))]
list_of_train = list_of_images[round(test_percentage*len(list_of_images)):]


os.mkdir('{}/train'.format(cwd))
os.mkdir('{}/test'.format(cwd))

for i in list_of_test:
    copyfile('{}/{}'.format(main_dir,i), '{}/test/{}'.format(cwd,i))
    copyfile('{}/{}json'.format(main_dir,i[:-3]), '{}/test/{}json'.format(cwd,i[:-3]))
    

for j in list_of_train:
    copyfile('{}/{}'.format(main_dir,j), '{}/train/{}'.format(cwd,j))
    copyfile('{}/{}json'.format(main_dir,j[:-3]), '{}/train/{}json'.format(cwd,j[:-3]))