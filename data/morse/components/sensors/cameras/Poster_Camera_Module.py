import sys, os
import GameLogic
import VideoTexture
import array, struct

import time
from Camera_Poster import ors_viam_poster
from Convert import convert
from datetime import datetime;
from helpers.MorseTransformation import Transformation3d

try:
   scriptRoot = os.path.join(os.environ['ORS_ROOT'],'scripts')
except KeyError:
   scriptRoot = '.'

try:
   libRoot = os.path.join(os.environ['ORS_ROOT'],'lib')
except KeyError:
   libRoot = '.'

if scriptRoot not in sys.path:
	sys.path.append(scriptRoot)
if scriptRoot not in sys.path:
	sys.path.append(libRoot)

from middleware.independent.IndependentBlender import *
import setup.ObjectData

#import ors_image_yarp
#from Convert import convert

structObject = ''
# Default size for an image of 512 * 512
Image_Size_X = 640
Image_Size_Y = 480
Nb_image = 1
Image_Size = 4 * Image_Size_X * Image_Size_Y

# Background color for the captured images (Default is blue)
#bg_color = [0, 0, 255, 255]
# Gray
bg_color = [143,143,143,255]

def init(contr):
	global structObject
	global Image_Size_X
	global Image_Size_Y
	global Image_Size
	global Nb_image

	print ('######## CAMERA INITIALIZATION ########')

	# Get the object data
	ob, parent, port_name = setup.ObjectData.get_object_data(contr)

	robot_state_dict = GameLogic.robotDict[parent]
	# Middleware initialization
	if not hasattr(GameLogic, 'orsConnector'):
		GameLogic.orsConnector = MiddlewareConnector()
		
	#Create Connection port
	try:
		#GameLogic.orsConnector.registerBufferedPortImageRgb([port_name])
		#GameLogic.orsConnector.registerBufferedPortBottle([port_name])
		GameLogic.orsConnector.registerPort([port_name])
	except NotImplementedError as detail:
		print ("ERROR: Unable to create the port:")
		print (detail)

	# Create a key for a dictionary of first_camera
	#  necesary if there are more than one camera added to the scene
	key = 'Camera'
	if GameLogic.pythonVersion < 3:
		screen_name = 'OBCameraCube'
		camera_name = 'OBCameraRobot'
	else:
		screen_name = 'CameraCube'
		camera_name = 'CameraRobot'
	texture_name = 'IMplasma.png'
	name_len = len(ob.name)
	if name_len > 4 and ob.name.endswith('.00', name_len-4, name_len-1):
		extension = ob.name[name_len-4:]
		key = key + extension
		screen_name = screen_name + extension
		camera_name = camera_name + extension
		#texture_name = texture_name + extension
	# Store the key as an ID in the Empty object
	ob['camID'] = key
	print ("Camera: Key being used is: '{0}'".format(key))

	# Get the reference to the camera and screen
	scene = GameLogic.getCurrentScene()
	screen = scene.objects[screen_name]
	camera = scene.objects[camera_name]

	# Link the objects using VideoTexture	
	if not hasattr(GameLogic, 'tv'):
		GameLogic.tv = {}

	matID = VideoTexture.materialID(screen, texture_name)	
	GameLogic.tv[key] = VideoTexture.Texture(screen, matID)
	GameLogic.tv[key].source = VideoTexture.ImageRender(scene,camera)

	#### WARNING 2.5 ####
	# As of 19 / 03 / 2010 Blender 2.5 is crashing when trying
	#  to export images of size 512 X 512
	# Temporarily restricting the size to 256 X 256
	if GameLogic.pythonVersion > 3:
		Image_Size_X = 256
		Image_Size_Y = 256
		Image_Size = 4 * Image_Size_X * Image_Size_Y

	# Set the background to be used for the render
	GameLogic.tv[key].source.background = bg_color
	# Define an image size. It must be powers of two. Default 512 * 512
	GameLogic.tv[key].source.capsize = [Image_Size_X, Image_Size_Y]
	print ("Camera: Exporting an image of capsize: {0} pixels".format(GameLogic.tv[key].source.capsize))

	# Set a filter to produce images in grayscale
	# NOT YET IMPLEMENTED IN BLENDER.
	#GameLogic.tv[key].source.filter = Gray

	# Create an instance of the Struct object,
	# to make the unpacking of the captured images more efficient
	structObject = struct.Struct('=BBB')

	# Check that the conversion buffer could be initialized
	#if not convert.init_array(Image_Size):
		#ob['Init_OK'] = True
	ob['Init_OK'] = True


	### POCOLIBS ###
	# Start the external poster module
	poster_name = "morse_" + ob['Component_Type'] + "_poster"
	poster_name = poster_name.upper()
	first_camera = ors_viam_poster.simu_image_init()
	first_camera.camera_name = "Left"
	first_camera.width = Image_Size_X
	first_camera.height = Image_Size_Y
	robot_state_dict[port_name] = ors_viam_poster.init_data(poster_name, "stereo_bank", Nb_image, 0, first_camera, None)
	print ("Poster ID generated: {0}".format(robot_state_dict[port_name]))
	if robot_state_dict[port_name] == None:
		print ("ERROR creating poster. This module may not work")
		ob['Init_OK'] = False


	#print_properties(ob)

	print ('######## CAMERA INITIALIZED ########')


def print_properties(ob):
	# Read the list of properties
	properties = ob.getPropertyNames()

	print ("Properties of object: " + ob)
	for prop in properties:
		print (prop + " = " + ob[prop])


def update(contr):
	ob = contr.owner

	# refresh video
	if hasattr(GameLogic, 'tv') and ob['Init_OK']:
		GameLogic.tv[ob['camID']].refresh(True)


# Conversion from a string to an array of integers
# From the blender image format to that of YARP
def decode_image (image_string):
	"""	Remove the alpha channel from the images taken from Blender.
		Convert the binary images to an array of integers, to be
		passed to the middleware.
		NOTE: Changing to an array of integers is not necessary
			Could possibly keep using a string. Need testing."""
	length = len(image_string)
	image_buffer = []
	k = 0

	# Grab 4 bytes of data, representing a single pixel
	for i in range(0, length, 4):
		rgb = structObject.unpack(image_string[i:i+3])
		image_buffer.extend ( rgb )

	return image_buffer


def grab(contr):
	""" Capture the image currently viewed by the camera.
		Convert the image and send it trough a port. """
	# Get the object data
	ob, parent, port_name = setup.ObjectData.get_object_data(contr)
	robot_state_dict = GameLogic.robotDict[parent]

	if ob['Init_OK']:
		# execute only when the 'grab_image' key is released
		# (if we don't test that, the code get executed two times,
		#	when pressed, and when released)
		sensor = GameLogic.getCurrentController().sensors['Check_capturing']

		if sensor.positive:
			# extract VideoTexture image
			if hasattr(GameLogic, 'tv'):
				imX,imY = GameLogic.tv[ob['camID']].source.size
				image_string = GameLogic.tv[ob['camID']].source.image

				# USING THE C LIBRARY TO CONVERT THE IMAGE FORMAT
				# The SWIG binding extracts the length of the string
				# info = convert.convert_image( image_string )
				"""
				GameLogic.orsConnector.postImageRGB(info, imX, imY, port_name)

				# Don't do any conversion, send the image as RGBA (yarp 2.2.5)
				data = array.array('B',image_string)
				info = data.buffer_info()
				GameLogic.orsConnector.postImageRGBA(info, imX, imY, port_name)
				"""

				"""
				# Data conversion in Python (OLD and SLOW)
				buf = decode_image (image_string)
				# Convert it to a form where we have access to a memory pointer
				data = array.array('B',buf)
				info = data.buffer_info()
				GameLogic.orsConnector.postImageRGB(info, imX, imY, port_name)
				"""

				### POCOLIBS ###
				mainToOrigin = Transformation3d(parent)
				sensorToOrigin = Transformation3d(ob)
				mainToSensor = mainToOrigin.transformation3dWith(sensorToOrigin)

				pom_robot_position =  ors_viam_poster.pom_position()
				pom_robot_position.x = mainToOrigin.x
				pom_robot_position.y = mainToOrigin.y
				pom_robot_position.z = mainToOrigin.z

				## TODO must we get the information from robot_state_dict or
				## just get the real value from the simulator
				pom_robot_position.yaw = robot_state_dict['Yaw']
				pom_robot_position.pitch = robot_state_dict['Pitch']
				pom_robot_position.roll = robot_state_dict['Roll']

				# Compute the current time ( we only requiere that the pom date
				# increases using a constant step so real time is ok)
				t = datetime.now()
				pom_date = int(t.hour * 3600* 1000 + t.minute * 60 * 1000 + 
					      t.second * 1000 + t.microsecond / 1000)

				first_camera = ors_viam_poster.simu_image()
				first_camera.width = Image_Size_X
				first_camera.height = Image_Size_Y
				first_camera.pom_tag = pom_date
				first_camera.tacq_sec = t.second
				first_camera.tacq_usec = t.microsecond
				first_camera.sensor = ors_viam_poster.pom_position()
				first_camera.sensor.x = mainToSensor.x
				first_camera.sensor.y = mainToSensor.y
				first_camera.sensor.z = mainToSensor.z
				first_camera.sensor.yaw = mainToSensor.yaw
				first_camera.sensor.pitch = mainToSensor.pitch
				first_camera.sensor.roll = mainToSensor.roll
#				first_camera.image_data = image_string

				posted = ors_viam_poster.post_viam_poster(robot_state_dict[port_name], 
						pom_robot_position, 1, first_camera, image_string, None, None)



def finish(contr):
	""" Procedures to kill the module when the program exits.
		12 / 04 / 2010
		Done for testing the closing of the poster. """

	ob, parent, port_name = setup.ObjectData.get_object_data(contr)
	robot_state_dict = GameLogic.robotDict[parent]

	print ("Component: {0} => Closing poster with id: {1}".format(ob, robot_state_dict[port_name]))
	ors_viam_poster.finalize(robot_state_dict[port_name])
	# Set the variable so that further calls to the main function will exit
	ob['Init_OK'] = False
	print ("Done!")

