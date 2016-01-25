"""Tango log reader API"""

# Author: Sudeep Pillai <spillai@csail.mit.edu>
# License: MIT

import numpy as np
import cv2
import os.path

from collections import Counter
from bot_externals.log_utils import Decoder, LogReader
from bot_vision.image_utils import im_resize
from bot_vision.imshow_utils import imshow_cv
from bot_geometry.rigid_transform import RigidTransform

def TangoOdomDecoder(channel, every_k_frames=1): 
    def odom_decode(data): 
        """ x, y, z, qx, qy, qz, qw, status_code, confidence, accuracy """
        p = np.float64(data.split(','))
        tvec, ori = p[:3], p[3:7]
        pose = RigidTransform(xyzw=ori, tvec=tvec)
        
        # Rotate camera reference with a rotation about x axis (+ve)
        p_roll = RigidTransform.from_roll_pitch_yaw_x_y_z(np.pi/2, 0, 0, 0, 0, 0)

        # Rotation now defined wrt camera (originally device)
        pose_CD = RigidTransform.from_roll_pitch_yaw_x_y_z(np.pi, 0, 0, 0, 0, 0) 
        
        return p_roll * pose * pose_CD
            
    return Decoder(channel=channel, every_k_frames=every_k_frames, decode_cb=lambda data: odom_decode(data))

class TangoImageDecoder(Decoder): 
    """
    """
    def __init__(self, directory, channel='RGB', every_k_frames=1, scale=1.): 
        Decoder.__init__(self, channel=channel, every_k_frames=every_k_frames)
        self.scale = scale
        self.directory = directory

    def decode(self, msg): 
        fn = os.path.join(self.directory, msg)
        if os.path.exists(fn): 
            im = cv2.imread(fn, cv2.CV_LOAD_IMAGE_COLOR)
            return im_resize(im, scale=self.scale)
        else: 
            raise Exception()

class TangoLogReader(LogReader): 
    def __init__(self, directory, scale=1.): 
        
        # Set directory and filename for time synchronized log reads 
        self.directory_ = os.path.expanduser(directory)
        self.filename_ = os.path.join(self.directory_, 'tango_data.txt')
        self.scale_ = scale
        
        # Initialize TangoLogReader with appropriate decoders
        super(TangoLogReader, self).__init__(self.filename_, 
                                             decoder=[
                                                 TangoOdomDecoder(channel='RGB_VIO'), 
                                                 TangoImageDecoder(self.directory_, channel='RGB', scale=scale)
                                             ])
        
        if self.start_idx < 0 or self.start_idx > 100: 
            raise ValueError('start_idx in TangoReader expects a percentage [0,100], provided {:}'.format(self.start_idx))

    def load_log(self, filename): 
        class TangoLog(object): 
            def __init__(self, filename): 
                self.meta_ =  open(filename, 'r')
                topics = map(lambda (t,ch,data): ch, 
                             filter(lambda ch: len(ch) == 3, 
                                    map(lambda l: l.replace('\n','').split('\t'), 
                                        filter(lambda l: '\n' in l, self.meta_.readlines()))))

                # Save topics and counts
                c = Counter(topics)
                self.topics_ = list(set(topics))
                self.topic_lengths_ = dict(c.items())
                
                messages_str = ', '.join(['{:} ({:})'.format(k,v) for k,v in c.iteritems()])
                print('\nTangoLog\n========\n\tTopics: {:}\n\tMessages: {:}\n'.format(self.topics_, messages_str))
                self.meta_.seek(0)

            def read_messages(self, topics=None, start_time=0): 
                for l in self.meta_:
                    try: 
                        t, ch, data = l.replace('\n', '').split('\t')
                    except: 
                        continue
                    yield ch, data, t

        return TangoLog(filename)

    def iteritems(self, reverse=False): 
        if self.index is not None: 
            raise NotImplementedError('Cannot provide items indexed')
        else: 
            if reverse: 
                raise RuntimeError('Cannot provide items in reverse when file is not indexed')

            # # Decode only messages that are supposed to be decoded 
            # # print self._log.get_message_count(topic_filters=self.decoder_keys())
            # st, end = self.log.get_start_time(), self.log.get_end_time()
            # start_t = Time(st + (end-st) * self.start_idx / 100.0)
             
            print('Reading TangoLog from {:3.2f}% onwards'.format(self.start_idx))
            for self.idx, (channel, msg, t) in enumerate(self.log.read_messages()):
                res, msg = self.decode_msg(channel, msg, t)
                if res: 
                    yield msg
                
    def decode_msg(self, channel, data, t): 
        try: 
            # Check if log index has reached desired start index, 
            # and only then check if decode necessary  
            dec = self.decoder[channel]
            if dec.should_decode():
                return True, (t, channel, dec.decode(data))
        except Exception as e:
            pass
            # print e
            # raise RuntimeError('Failed to decode data from channel: %s, mis-specified decoder?' % channel)
        
        return False, (None, None)

    def iter_frames(self):
        return self.iteritems()

