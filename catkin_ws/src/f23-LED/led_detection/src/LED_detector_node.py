#!/usr/bin/env python
import rospy
import time
from led_detection.LEDDetector import LEDDetector
from std_msgs.msg import Byte
from duckietown_msgs.msg import Vector2D, LEDDetection, LEDDetectionArray, LEDDetectionDebugInfo
from sensor_msgs.msg import CompressedImage
from duckietown_utils.bag_logs import numpy_from_ros_compressed
import numpy as np

class LEDDetectorNode(object):
    def __init__(self):
        self.first_timestamp = 0 # won't start unless it's None
        self.data = []
        self.capture_time = 1 # capture time
        self.capture_finished = False
        self.tinit = None
        
        self.node_name = rospy.get_name()
        self.pub_detections = rospy.Publisher("~raw_led_detection",LEDDetectionArray,queue_size=1)
        self.pub_debug = rospy.Publisher("~debug_info",LEDDetectionDebugInfo,queue_size=1)
        self.veh_name = rospy.get_namespace().strip("/")
        rospy.loginfo('Vehicle: %s'%self.veh_name)
        self.sub_cam = rospy.Subscriber("camera_node/image/compressed",CompressedImage, self.camera_callback)
        self.sub_cam = rospy.Subscriber("~trigger",Byte, self.trigger_callback)
        print('Waiting for camera image...')

    def camera_callback(self, msg):
        float_time = msg.header.stamp.to_sec()

        if self.first_timestamp is None:
            self.data = []
            self.capture_finished = False
            rospy.loginfo('Start capturing frames')
            self.first_timestamp = msg.header.stamp.to_sec()
            self.tinit = time.time()
        # TODO sanity check rel_time positive, restart otherwise 
        rel_time = float_time - self.first_timestamp
        rospy.loginfo('Relative frame %s' %rel_time)
        debug_msg = LEDDetectionDebugInfo()
        if rel_time < self.capture_time:
            rgb = numpy_from_ros_compressed(msg)
            rospy.loginfo('Capturing frame %s' %rel_time)
            self.data.append({'timestamp': float_time, 'rgb': rgb})
            debug_msg.state = 1
            debug_msg.capture_progress = 100.0*rel_time/self.capture_time
            self.pub_debug.publish(debug_msg)

        elif not self.capture_finished:
            self.capture_finished = True
            debug_msg.state = 2
            self.pub_debug.publish(debug_msg)
            self.process_and_publish()

    def trigger_callback(self, msg):
        self.first_timestamp = None

    def process_and_publish(self):
        # TODO add check timestamps for dropped frames
        H, W, _ = self.data[0]['rgb'].shape
        n = len(self.data)
        dtype = [
            ('timestamp', 'float'),
            ('rgb', 'uint8', (H, W, 3)),
        ]
        images = np.zeros((n,), dtype=dtype)
        for i, v in enumerate(self.data):
            images[i]['timestamp'] = v['timestamp']
            images[i]['rgb'][:] = v['rgb']
        
        det = LEDDetector(False, False, False, self.pub_debug)
        rgb0 = self.data[0]['rgb']
        mask = np.ones(dtype='bool', shape=rgb0.shape)
        tic = time.time()
        result = det.detect_led(images, mask, [2.8, 4.1, 5.0], 5)
        self.pub_detections.publish(result)
        toc = time.time()-tic
        tac = time.time()-self.tinit
        print('Done. Processing Time: %.2f'%toc)
        print('Total Time taken: %.2f'%tac)

if __name__ == '__main__':
    rospy.init_node('LED_detector_node',anonymous=False)
    node = LEDDetectorNode()
    rospy.spin()
