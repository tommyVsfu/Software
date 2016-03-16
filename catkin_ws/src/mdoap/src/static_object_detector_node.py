#!/usr/bin/env python
import cv2
import numpy as np
import rospy
from sensor_msgs.msg import CompressedImage, Image
from std_msgs.msg import Float32
from cv_bridge import CvBridge, CvBridgeError
from duckietown_msgs.msg import ObstacleImageDetection, ObstacleImageDetectionList, ObstacleType, Rect
import sys
import threading


class Matcher:
    def __init__(self):
        template_loc = rospy.get_param("~template")
        rospy.loginfo("Template location: "+template_loc)
        template = cv2.imread(template_loc)
        if template == None:
            print "\n\nno image template found at %s, \
            enter complete path for template image\n\n" % template_loc
            sys.exit(1)
        self.h, self.w, _= template.shape
        pyramid_len =5  # enter number higher than zero for pyramid matching
        self.templates = [(1, template)]
        # Use pyramid for matching template.  Create resized copies
        # of template image:
        for i in range(2, pyramid_len):
            if i == 0: continue
            self.templates.append(\
                    (1.0/i, cv2.resize(template, (self.w/i, self.h/i ))))
            self.templates.append(\
                    (i, cv2.resize(template, (self.w*i, self.h*i ))))
        self.method = cv2.TM_SQDIFF_NORMED


    def template_match(self, img):
        results = []
        for  (adjust, template)  in self.templates:
            t_h, t_w, _ = template.shape
            if t_h > self.h or t_w > self.w: continue
            res = cv2.matchTemplate(img,template,self.method)
            min_val, _ , top_left, _  = cv2.minMaxLoc(res)
            results.append( (min_val, template, top_left))

        # sort all images to find the best match.
        results.sort()
        # min val shows accuracy of each template match. 
        # it is normalized from 0 to 1.  The smaller the better.
        min_val, template, top_left = results[0]
        
        if min_val < .5: 
            # draw a box around the best match
            t_h, t_w, _ =  template.shape
            bottom_right = (top_left[0] + t_w, top_left[1] + t_h)
            cv2.rectangle(img,top_left, bottom_right, 255, 4)
            width = img.shape[1]
            # compute relative offset from center
            pose = .5 -( (width-(top_left[0] + .5*t_h)) / width )
        else:
            pose = float('nan')
        return img, pose

    def contour_match(self, img):
        '''
        Returns 1. Image with bounding boxes added
                2. an ObstacleImageDetectionList
        '''

        object_list = ObstacleImageDetectionList()
        object_list.list = []

        height,width = img.shape[:2]
        hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        COLOR_MIN = np.array([0, 80, 80],np.uint8)
        COLOR_MAX = np.array([22, 255, 255],np.uint8)
        frame_threshed = cv2.inRange(hsv_img, COLOR_MIN, COLOR_MAX)
        imgray = frame_threshed
        ret,thresh = cv2.threshold(frame_threshed,22,255,0)
        try:
            contours, hierarchy = cv2.findContours(\
                    thresh,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)

            # Find the index of the largest contour
            areas = [cv2.contourArea(c) for c in contours]
            max_index = np.argmax(areas)
            cnt = contours[max_index]
            contour_area = [ (cv2.contourArea(c), (c) ) for c in contours]
            #contour_area.sort()
            contour_area = sorted(contour_area,reverse=True, key=lambda x: x[0])
            for (area,(cnt)) in contour_area[:10]:
            # plot box around contour
                x,y,w,h = cv2.boundingRect(cnt)
                d =  0.5*(x-width/2)**2 + (y-height)**2 
                if h>15 and w >15 and d  < 120000:
                    r = Rect()
                    r.x = x
                    r.y = y
                    r.w = w
                    r.h = h
                    t = ObstacleType()
                    #TODO(??): Assign type based on color
                    t.type = ObstacleType.CONE
                    d = ObstacleImageDetection()
                    d.bounding_box = r
                    d.type = t

                    object_list.list.append(d);
                    cv2.rectangle(img,(x,y),(x+w,y+h),(0,255,0),2)
        except:
            print "contr err"
        return img, object_list

class StaticObjectDetectorNode:
    def __init__(self, target_img="cone.png"):
        self.name = 'static_object_detector_node'
        

        self.tm = Matcher()
        self.thread_lock = threading.Lock()
        self.sub_image = rospy.Subscriber("~image_compressed", CompressedImage, self.cbImage, queue_size=1)
        self.pub_image = rospy.Publisher("~cone_detection_image", Image, queue_size=1)
        self.pub_detections_list = rospy.Publisher("~object_image_detection_list", ObstacleImageDetectionList, queue_size=1)
        self.bridge = CvBridge()

        rospy.loginfo("[%s] Initialized." %(self.name))

    def cbImage(self,image_msg):
        thread = threading.Thread(target=self.processImage,args=(image_msg,))
        thread.setDaemon(True)
        thread.start()

    def processImage(self, image_msg):
        if not self.thread_lock.acquire(False):
            return

        np_arr = np.fromstring(image_msg.data, np.uint8)
        
        image_cv = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        img, detections = self.tm.contour_match(image_cv)
        detections.header.stamp = image_msg.header.stamp
        detections.header.frame_id = image_msg.header.frame_id
        self.pub_detections_list.publish(detections)
        height,width = img.shape[:2]
        try:
            self.pub_image.publish(self.bridge.cv2_to_imgmsg(img, "bgr8"))
        except CvBridgeError as e:
            print(e)

        self.thread_lock.release()

if __name__=="__main__":
	rospy.init_node('static_object_detector_node')
	node = StaticObjectDetectorNode()
	rospy.spin()