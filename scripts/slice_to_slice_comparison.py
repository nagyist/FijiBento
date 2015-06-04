# Setup
import utils
import models
import ransac
import os
import numpy as np
import matplotlib.pyplot as plt
import h5py
import json
import random
import math
import sys
import getopt
import operator
from scipy.spatial import Delaunay
from scipy.spatial import distance
from scipy.spatial import KDTree
import cv2
import time
import glob
# os.chdir("C:/Users/Raahil/Documents/Research2015_eclipse/Testing")
os.chdir("/data/SCS_2015-4-27_C1w7_alignment")


def secondlargest(nums):
    largest = -1
    secondlarge = -2
    for index in range(0, len(nums)):
        if nums[index] > largest:
            secondlarge = largest
            largest = nums[index]
        elif nums[index] > secondlarge:
            secondlarge = nums[index]
    return secondlarge


def thirdlargest(nums):
    largest = -1
    secondlarge = -2
    thirdlarge = -3
    for index in range(0, len(nums)):
        if nums[index] > largest:
            thirdlarge = secondlarge
            secondlarge = largest
            largest = nums[index]
        elif nums[index] > secondlarge:
            thirdlarge = secondlarge
            secondlarge = nums[index]
        elif nums[index] > thirdlarge:
            thirdlarge = nums[index]
    return thirdlarge


def analyzeimg(slicenumber, mfovnumber, num, data):
    slicestring = ("%03d" % slicenumber)
    numstring = ("%03d" % num)
    mfovstring = ("%06d" % mfovnumber)
    imgname = "2d_work_dir/W01_Sec" + slicestring + "/W01_Sec" + slicestring + "_sifts_" + slicestring + "_" + mfovstring + "_" + numstring + "*"
    f = h5py.File(glob.glob(imgname)[0], 'r')
    resps = f['pts']['responses'][:]
    descs = f['descs'][:]
    octas = f['pts']['octaves'][:]
    jsonindex = (mfovnumber - 1) * 61 + num - 1
    xtransform = float(data[jsonindex]["transforms"][0]["dataString"].encode("ascii").split(" ")[0])
    ytransform = float(data[jsonindex]["transforms"][0]["dataString"].encode("ascii").split(" ")[1])

    xlocs = []
    ylocs = []
    if len(resps) != 0:
        xlocs = f['pts']['locations'][:, 0] + xtransform
        ylocs = f['pts']['locations'][:, 1] + ytransform

    allpoints = []
    allresps = []
    alldescs = []
    for pointindex in range(0, len(xlocs)):
        currentocta = int(octas[pointindex]) & 255
        if currentocta > 128:
            currentocta -= 255
        if currentocta == 4 or currentocta == 5:
            allpoints.append(np.array([xlocs[pointindex], ylocs[pointindex]]))
            allresps.append(resps[pointindex])
            alldescs.append(descs[pointindex])
    points = np.array(allpoints).reshape((len(allpoints), 2))
    return (points, allresps, alldescs)


def getcenter(slicenumber, mfovnumber, data):
    xlocsum, ylocsum, nump = 0, 0, 0
    for num in range(1, 62):
        jsonindex = (mfovnumber - 1) * 61 + num - 1
        xlocsum += data[jsonindex]["bbox"][0] + data[jsonindex]["bbox"][1]
        ylocsum += data[jsonindex]["bbox"][2] + data[jsonindex]["bbox"][3]
        nump += 2
    return [xlocsum / nump, ylocsum / nump]


def reorienttris(trilist, pointlist):
    for num in range(0, trilist.shape[0]):
        v0 = np.array(pointlist[trilist[num][0]])
        v1 = np.array(pointlist[trilist[num][1]])
        v2 = np.array(pointlist[trilist[num][2]])
        if np.cross((v1 - v0), (v2 - v0)) < 0:
            trilist[num][0], trilist[num][1] = trilist[num][1], trilist[num][0]
    return


def analyzemfov(slicenumber, mfovnumber, maximgs, data):
    allpoints = np.array([]).reshape((0, 2))
    allresps = []
    alldescs = []
    for i in range(1, maximgs + 1):
        (tempoints, tempresps, tempdescs) = analyzeimg(slicenumber, mfovnumber, i, data)
        allpoints = np.append(allpoints, tempoints, axis=0)
        allresps += tempresps
        alldescs += tempdescs
    allpoints = np.array(allpoints)
    return (allpoints, allresps, alldescs)


def generatematches_cv2(allpoints1, allpoints2, alldescs1, alldescs2):
    matcher = cv2.BFMatcher()
    matches = matcher.knnMatch(np.array(alldescs1), np.array(alldescs2), k=2)
    goodmatches = []
    for m, n in matches:
        if m.distance / n.distance < 0.92:
            goodmatches.append([m])
    match_points = np.array([
        np.array([allpoints1[[m[0].queryIdx for m in goodmatches]]][0]),
        np.array([allpoints2[[m[0].trainIdx for m in goodmatches]]][0])])
    return match_points


def generatematches_brute(allpoints1, allpoints2, alldescs1, alldescs2):
    bestpoints1 = []
    bestpoints2 = []
    for pointrange in range(0, len(allpoints1)):
        selectedpoint = allpoints1[pointrange]
        selectedpointd = alldescs1[pointrange]
        bestdistsofar = sys.float_info.max - 1
        secondbestdistsofar = sys.float_info.max
        bestcomparedpoint = allpoints2[0]
        distances = []
        for num in range(0, len(allpoints2)):
            comparedpointd = alldescs2[num]
            bestdist = distance.euclidean(selectedpointd.astype(np.int), comparedpointd.astype(np.int))
            distances.append(bestdist)
            if bestdist < bestdistsofar:
                secondbestdistsofar = bestdistsofar
                bestdistsofar = bestdist
                bestcomparedpoint = allpoints2[num]
            elif bestdist < secondbestdistsofar:
                secondbestdistsofar = bestdist
        if bestdistsofar / secondbestdistsofar < .92:
            bestpoints1.append(selectedpoint)
            bestpoints2.append(bestcomparedpoint)
    match_points = np.array([bestpoints1, bestpoints2])
    return match_points


def analyze2slicesmfovs(slice1, mfov1, slice2, mfov2, data1, data2):
    print str(slice1) + "-" + str(mfov1) + " vs. " + str(slice2) + "-" + str(mfov2)
    (allpoints1, allresps1, alldescs1) = analyzemfov(slice1, mfov1, 61, data1)
    (allpoints2, allresps2, alldescs2) = analyzemfov(slice2, mfov2, 61, data2)
    match_points = generatematches_cv2(allpoints1, allpoints2, alldescs1, alldescs2)
    model_index = 1
    iterations = 2000
    max_epsilon = 500
    min_inlier_ratio = 0
    min_num_inlier = 7
    max_trust = 3
    model, filtered_matches = ransac.filter_matches(match_points, model_index, iterations, max_epsilon, min_inlier_ratio, min_num_inlier, max_trust)
    if filtered_matches is None:
        filtered_matches = np.zeros((0, 0))
    return (model, filtered_matches.shape[1], float(filtered_matches.shape[1]) / match_points.shape[1], match_points.shape[1], len(allpoints1), len(allpoints2))


def analyze2slices(slice1, slice2, data1, data2, nummfovs):
    toret = []
    modelarr = np.zeros((nummfovs, nummfovs), dtype=models.RigidModel)
    numfilterarr = np.zeros((nummfovs, nummfovs))
    filterratearr = np.zeros((nummfovs, nummfovs))
    besttransform = None

    while besttransform is None:
        mfov1 = random.randint(1, nummfovs)
        mfov2 = random.randint(1, nummfovs)
        (model, num_filtered, filter_rate, num_rod, num_m1, num_m2) = analyze2slicesmfovs(slice1, mfov1, slice2, mfov2, data1, data2)
        modelarr[mfov1 - 1, mfov2 - 1] = model
        numfilterarr[mfov1 - 1, mfov2 - 1] = num_filtered
        filterratearr[mfov1 - 1, mfov2 - 1] = filter_rate
        if num_filtered > 50 and filter_rate > 0.25:
            besttransform = model.get_matrix()
            break
    print "Preliminary Transform Found"

    for i in range(0, nummfovs):
        mycenter = getcenter(slice1, i + 1, data1)
        mycentertrans = np.dot(besttransform, np.append(mycenter, [1]))[0:2]
        distances = np.zeros(nummfovs)
        for j in range(0, nummfovs):
            distances[j] = np.linalg.norm(mycentertrans - getcenter(slice2, j + 1, data2))
        checkindices = distances.argsort()[0:7]
        for j in range(0, len(checkindices)):
            (model, num_filtered, filter_rate, num_rod, num_m1, num_m2) = analyze2slicesmfovs(slice1, i + 1, slice2, checkindices[j] + 1, data1, data2)
            modelarr[i, checkindices[j]] = model
            numfilterarr[i, checkindices[j]] = num_filtered
            filterratearr[i, checkindices[j]] = filter_rate
            if num_filtered > 50 and filter_rate > 0.25:
                besttransform = model.get_matrix()
                dictentry = {}
                dictentry['mfov1'] = i + 1
                dictentry['mfov2'] = slice2
                dictentry['features_in_mfov1'] = num_m1
                dictentry['features_in_mfov2'] = num_m2
                dictentry['transformation'] = {
                    "className": model.class_name,
                    "matrix": besttransform.tolist()
                }
                dictentry['matches_rod'] = num_rod
                dictentry['matches_model'] = num_filtered
                dictentry['filter_rate'] = filter_rate
                toret.append(dictentry)
                break
    return toret


def main():
    script, slice1, slice2, nummfovs = sys.argv
    starttime = time.clock()
    slice1 = int(slice1)
    slice2 = int(slice2)
    nummfovs = int(nummfovs)
    slicestring1 = ("%03d" % slice1)
    slicestring2 = ("%03d" % slice2)
    with open("tilespecs/W01_Sec" + slicestring1 + ".json") as data_file1:
        data1 = json.load(data_file1)
    with open("tilespecs/W01_Sec" + slicestring2 + ".json") as data_file2:
        data2 = json.load(data_file2)
    retval = analyze2slices(slice1, slice2, data1, data2, nummfovs)

    jsonfile = {}
    jsonfile['tilespec1'] = "file://" + os.getcwd() + "/tilespecs/W01_Sec" + ("%03d" % slice1) + ".json"
    jsonfile['tilespec2'] = "file://" + os.getcwd() + "/tilespecs/W01_Sec" + ("%03d" % slice2) + ".json"
    jsonfile['matches'] = retval
    jsonfile['runtime'] = time.clock() - starttime
    os.chdir("/home/raahilsha")
    json.dump(jsonfile, open("Slice" + str(slice1) + "vs" + str(slice2) + ".json", 'w'), indent=4)

if __name__ == '__main__':
    main()