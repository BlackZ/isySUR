# -*- coding: utf-8 -*-
"""
Created on Tue Jan 13 19:35:17 2015

@author: Thorsten
"""
from math import cos
_relativeNullPoint=(0.0,0.0)

def getXYpos(relativeNullPoint,p):
  """ 
    Calculates X and Y distances in meters.

    @param relativeNullPoint: The relative null point for the calculation.
    @type relativeNullPoint: Tupel(float,float)
    
    @param p: Point (lat,long) for which the x,y position should be calculated.
    @type p: Tupel(float,float)
    
    @return: Tupel with x,y coordinates of the given point.
    @rtype: Tupel(float,float)
  """    
  deltaLatitude = p[0] - relativeNullPoint[0]
  deltaLongitude = p[1] - relativeNullPoint[1]
  latitudeCircumference = 40075160 * cos(relativeNullPoint[0])
  resultX = deltaLongitude * latitudeCircumference / 360
  resultY = deltaLatitude * 40008000 / 360
  return (resultX, resultY)