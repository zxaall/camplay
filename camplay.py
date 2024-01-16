# camplay  - shows live video from camera and camera-alike devices
#           can record videos without sound and take stapshots
# Copyright(C)  Val Krigan, MIT, see LICENSE file

import sys, os, time
from datetime import datetime
import cv2
import tkinter as tk
from tkinter import simpledialog
from PIL import Image, ImageTk

# global constants and varibles
record_folder = "./camplay"  # Predefined folder for recording
initial_fps = None  # recording fps, if None then as is from the camera
codec_str = 'mp4v' # H264 mp4v
video_fourcc = cv2.VideoWriter_fourcc(*codec_str)  # Use 'mp4v' for MP4 format
video_ext = "mp4"   # video recording extensions, defines file format
image_ext = "jpg"   # snapshots' extensions, defines encoding format, can be png, tiff..
verbose = False     # add some info output to stdout

default_camera_index = 0
#default_resolutions = ["640x480", "800x600", "1024x768", "1280x720", "1920x1080"]
default_resolutions = ["160x120", "320x240", "640x480", "800x600", "1280x720", "1920x1080"]
zoom_scale = 1.2

sticky_scroll = True  # if scroll point sticks to finger/mouse

# Function to draw a red cross on the frame
def draw_red_cross(frame, pos=None):
    center = (frame.shape[1] // 2, frame.shape[0] // 2)
    cv2.line(frame, (center[0] - 10, center[1]), (center[0] + 10, center[1]), (0, 0, 255), 2)
    cv2.line(frame, (center[0], center[1] - 10), (center[0], center[1] + 10), (0, 0, 255), 2)
    return frame

def draw_green_cross(frame, pos=None):
    if pos == None or not isinstance(pos, tuple):
        pos = (frame.shape[1] // 2, frame.shape[0] // 2)
    elif not isinstance(pos[0], int):
        # it's relative position
        pos = (int(frame.shape[1] * pos[0]), int(frame.shape[0] * pos[1]))
    size = 40//2
    cv2.line(frame, (pos[0] - size, pos[1]), (pos[0] + size, pos[1]), (0, 255, 0), 2)
    cv2.line(frame, (pos[0], pos[1] - size), (pos[0], pos[1] + size), (0, 255, 0), 2)
    return frame

# wraps cv2 camera in common interface
class  CameraCV2:
    # note: it's a class method, no self
    def check_camera(camera_index):
        # Attempt to open the first camera, 
        log_level = cv2.getLogLevel()
        cv2.setLogLevel(0)  # suppressing logs
        cap = cv2.VideoCapture(camera_index)
        cv2.setLogLevel(log_level)

        # Check if the camera is opened successfully
        if cap.isOpened():
            cap.release()  # Release the camera resource
            return True
        else:
            return False
    
    def __init__(self, cam_idx, start=False):
        self.idx = cam_idx
        self.id = None
        self.cap = None   # capture device, i.e. camera
        self.maxResolution = None
        if start:
            self.Open()
    
    # idx can be single value or a list of them, the first which works will be used
    def Open(self, idx=None):
        if idx:
            self.idx = idx
        else:
            idx = self.idx
        # if it's one of choise
        if '__len__' in dir(idx):  # which both list and tuple have
            for i in idx:
                id = int(i)
                if type(self).check_camera(id):
                    break
        else:
            id = idx
        #print("openning: ", id)
        
        # at this point idx is a single value, hope camera didn't get disconneted
        self.cap = cv2.VideoCapture(id)
        self.id = id

    def IsOpen(self):
        return  self.cap and self.cap.isOpened()
    
    def GetId(self):
        return self.id
    
    def Close(self):
        if self.cap:
            self.cap.release()
            self.cap = None
        self.id = None

    # returns (width, height)
    def GetResolution(self):
        return  self.cap.get(cv2.CAP_PROP_FRAME_WIDTH), self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    
    def SetResolution(self, width, height):
        return  self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width) \
            and self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)    

    # returns  (success, frame), success==False if reading frame fails
    def Read(self):
        return  self.cap.read()

    # makes sense only for video, photo cameras don't support it
    def GetFPS(self):
        self.cap.get(cv2.CAP_PROP_FPS)

    # returns [(width, height)] if supported by camera, othewise None
    def GetSupportedResolutions(self):
        return  None

    def GetMaxResolution(self):
        return  self.maxResolution
    
    # think: set ROI emulation with frame cropping
    # returns (x0,y0, width,height) of range of interest in original image
    # note: in current resolution. i.e. with resolution change ROI should
    #       be updated.
    def GetROI(self):  # for cv2 always full screen
        width, height = self.GetResolution()
        return  (0,0, width, height)
    
    def SetROI(self, x0, y0, width, height):
        return  False   # not supported for cv2
    
# recors video, frame by frame after setup
class RecorderCV2:
    pass


# visualizer with some callback hooks, all features
# as UI it has it's own events loop. keep this in mind
class CamPlay:
    def __init__(self, cam_id=0, cam=None, resolutions=None, initial_res=None):
        global  draw_green_cross, draw_red_cross, record_folder
        # basic init
        self.cam = cam
        self.camera_index = cam_id
        self.frame_proc = draw_green_cross
        self.draw_red_cross = draw_red_cross

        # init in this order:
        self.init_params(resolutions=resolutions, initial_res=initial_res)
        self.init_camera()
        self.init_window()
        self.init_buttons()

    def init_params(self, resolutions=None, initial_res=None):
        # more or less static constants and varibles
        self.record_folder = record_folder  # Predefined folder for recording
        self.initial_fps = None  # recording fps, if None then as is from the camera
        self.codec_str = 'mp4v' # H264 mp4v
        self.video_fourcc = cv2.VideoWriter_fourcc(*codec_str)  # Use 'mp4v' for MP4 format
        self.video_ext = "mp4"   # video recording extensions, defines file format
        self.image_ext = "jpg"   # snapshots' extensions, defines encoding format, can be png, tiff..
        self.verbose = False     # add some info output to stdout

        global default_resolutions 
        self.common_resolutions = resolutions if resolutions else default_resolutions
        self.initial_resolution = initial_res
        self.zoom_scale = 1.2

        # if scroll point sticks to finger/mouse
        self.sticky_scroll = True  

        # Initialize variables, runtime
        self.play = True  # Variable to toggle play and stop
        self.full_screen = False  # Variable to track full-screen state
        self.red_cross = False  # Variable to toggle red cross drawing
        self.my_proc = False  # toggle frame_proc call
        self.recording = False
        self.video_writer = None
        self.fps = None  # current fps
        self.snap_next = False  # save next frame
        # Variables for zoom and scroll
        self.zoom_factor = 1.0
        self.offset_x, self.offset_y = 0, 0
        self.prev_x, self.prev_y = 0, 0
        self.me_pos = None
        self.scroll_path = None
        self.frame_shape = None
        self.image_zoom = 1.0  # how much frame is stratched, depends on windw size
        
        self.resolution_buttons = {}  # Dictionary to store resolution buttons
        self.current_resolution = None  # Variable to store the current resolution

        # Ensure the recording folder exists
        try:
            if not os.path.exists(self.record_folder):
                os.makedirs(self.record_folder)
        except Exception as e:
            print("creating folder exception: ", str(e))
        
        
    def init_camera(self):
        # Initialize the camera to default webcam
        if not self.cam:
            self.cam = CameraCV2(self.camera_index, start=True)
        
        if self.initial_resolution:
            self.initial_width, self.initial_height = map(int, self.initial_resolution.split('x'))
            self.cam.SetResolution(self.initial_width, self.initial_height)
        
        # Capture an initial frame to get the video size
        ret, self.frame = self.cam.Read()
        if not ret:
            print("Failed to grab frame")
            self.cam.Close()
            return  False
        #self.height, self.width, _ = frame.shape
        return  True
        
    def init_window(self):
        # Create a tkinter window with the size of the first frame
        self.window = tk.Tk()
        self.update_window_title()
        if self.cam.IsOpen():
            width, height = self.cam.GetResolution()
        else:
            if self.verbose: print(f"No camera found")
            width, height = 640, 480
        self.current_resolution = f"{width}x{height}"
        if self.verbose: print(f"initial settings: {self.current_resolution}")
        buttons_reserve = 108  # how much buttons take off the frame
        self.window.geometry(f"{int(width+buttons_reserve)}x{int(height)}")

        # Create a frame for video feed and buttons
        self.video_frame = tk.Frame(self.window)
        self.video_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.button_frame = tk.Frame(self.window)
        self.button_frame.pack(side=tk.RIGHT, fill=tk.Y)

        # Label for displaying the camera feed
        self.label = tk.Label(self.video_frame)
        self.label.pack(expand=True, fill=tk.BOTH)

        # Bind mouse events to the label
        #label.bind("<Button-1>", lambda e: handle_click(e, "click"))
        self.label.bind("<Double-Button-1>", lambda e: self.handle_click(e, "double"))

        # Bind mouse events for scrolling
        self.label.bind("<ButtonPress-1>", self.mouse_start_scroll)
        self.label.bind("<B1-Motion>", self.mouse_scroll)
        self.label.bind("<ButtonRelease-1>", self.mouse_end_click)

        # Bind mouse wheel event for zooming
        self.label.bind("<MouseWheel>", self.on_mouse_wheel)  # For Windows
        self.label.bind("<Button-4>", self.on_mouse_wheel)   # For Linux
        self.label.bind("<Button-5>", self.on_mouse_wheel)   # For Linux

        # Bind middle mouse button for reset zoom
        self.label.bind("<Button-2>", self.reset_zoom)

    def init_buttons(self):
        # Buttons
        self.btn_play_stop = tk.Button(self.button_frame, text="Play/Stop", command=self.toggle_play_stop)
        self.btn_play_stop.pack(fill=tk.X)

        self.btn_reconnect = tk.Button(self.button_frame, text="Reconnect", command=self.reconnect_camera)
        self.btn_reconnect.pack(fill=tk.X)

        self.btn_disconnect = tk.Button(self.button_frame, text="Disconnect", command=self.disconnect_camera)
        self.btn_disconnect.pack(fill=tk.X)

        self.btn_red_cross = tk.Button(self.button_frame, text="Red Cross", command=self.toggle_red_cross)
        self.btn_red_cross.pack(fill=tk.X, pady=(10, 0))

        self.btn_my_proc = tk.Button(self.button_frame, text="My proc", command=self.toggle_my_proc)
        self.btn_my_proc.pack(fill=tk.X)

        # Create a single button for zoom control
        self.btn_zoom = tk.Button(self.button_frame, text="-  1:1  +")
        self.btn_zoom.pack(fill=tk.X)
        self.btn_zoom.bind("<Button-1>", self.zoom_change)

        # Add snapshot button
        self.btn_snapshot = tk.Button(self.button_frame, text="Snapshot", command=self.take_snapshot)
        self.btn_snapshot.pack(fill=tk.X, pady=(20, 0))

        # Add record button
        self.btn_record = tk.Button(self.button_frame, text="Start", command=self.toggle_recording)
        self.btn_record.pack(fill=tk.X, pady=(0, 20))
        self.btn_record.config(text="Start", fg="red")
        self.btn_record.config(state='disabled')  # disabling for now, doesn't always work. :\

        self.btn_quit = tk.Button(self.button_frame, text="Quit", command=self.quit_application)
        self.btn_quit.pack(side=tk.BOTTOM, fill=tk.X, pady=(15, 0))

        # Create buttons for resolutions
        for res in self.common_resolutions[::-1]:
            btn = tk.Button(self.button_frame, text=res, command=lambda r=res: self.change_frame_size(r))
            btn.pack(side=tk.BOTTOM, fill=tk.X)
            self.resolution_buttons[res] = btn
            
        self.update_button_styles()
        
    def window_exists(self): # if it hasn't been closed
        return  self.window.winfo_exists()
    
    def quit_application(self):
        if self.recording:
            self.video_writer.release()
        self.window.quit()

    # Function to update the label with the camera feed
    def update_frame(self):
        if self.play and self.cam.IsOpen():
            ret, self.frame = self.cam.Read()
            #print(f"ret: {ret}, shape: {frame.shape if ret else None}")
            if ret:
                # Resize frame to fit the current window while maintaining aspect ratio
                def resize_frame():
                    #nonlocal  frame, snap_next, frame_shape, image_zoom 
                    nonlocal self
                    # all preprocess and recording after processing, but before scaling
                    if self.my_proc: 
                        self.frame = self.frame_proc(self.frame, self.me_pos)
                    if self.red_cross:
                        self.frame = self.draw_red_cross(self.frame)
                    if self.recording and self.video_writer:
                        self.video_writer.write(self.frame)  # cv2_frame is the raw frame from the camera
                    if self.snap_next:
                        self.snap_next = False
                        #global  record_folder, image_ext, verbose
                        now = datetime.now()
                        filename = now.strftime("snapshot_%Y-%m-%d_%H%M%S."+self.image_ext)
                        filepath = os.path.join(self.record_folder, filename)
                        cv2.imwrite(filepath, self.frame)
                        if self.verbose: print(f"Snapshot saved: {filename}")
                    self.frame_shape = self.frame.shape
                    
                    # applying zoom, for that cropping out area of interest
                    #nonlocal  offset_x, offset_y, zoom_factor
                    if self.zoom_factor != 1.0:
                        height, width, _ = self.frame.shape
                        cropped_frame = self.frame[int(self.offset_y):int(self.offset_y + height/self.zoom_factor),
                                            int(self.offset_x):int(self.offset_x + width/self.zoom_factor)]
                        #print("cropped shape: ", cropped_frame.shape)
                        try:
                            self.frame = cv2.resize(cropped_frame, (int(width), int(height)))                    
                        except Exception as e:
                            print("resize exception: ", str(e), "shape:", cropped_frame.shape, " ", width, "x", height)
                            #print(self.zoom_factor, "::", int(self.offset_y), int(self.offset_y + height/self.zoom_factor),
                            #                int(self.offset_x), int(self.offset_x + width/self.zoom_factor))
                    
                    # Resize frame to fit the current window while maintaining aspect ratio
                    self.window.update_idletasks()  # Update window to get current sizes
                    window_width = self.window.winfo_width() - self.button_frame.winfo_width()
                    window_height = self.window.winfo_height()
                    scale_w = window_width / self.frame.shape[1]
                    scale_h = window_height / self.frame.shape[0]
                    scale = min(scale_w, scale_h)
                    self.image_zoom = scale
                    frame_resized = cv2.resize(self.frame, (int(self.frame.shape[1] * scale)-2, int(self.frame.shape[0] * scale)-2))
                    frame_resized = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
                    im = Image.fromarray(frame_resized)
                    img = ImageTk.PhotoImage(image=im)
                    self.label.imgtk = img
                    self.label.config(image=img)
                self.window.after(1, resize_frame)
        #nonlocal button_frame
        #print("width: ", button_frame.winfo_width())
        self.label.after(10, self.update_frame)

    def run(self):
        # Start the update loop
        self.update_frame()

        # Start the tkinter mainloop
        self.window.mainloop()

        # Release the camera when the window is closed
        self.cam.Close()
        
    # Function to reconnect the camera
    def reconnect_camera(self):
        self.cam.Close()
        self.cam.Open()
        for btn in self.resolution_buttons.values():
            btn.config(state='normal', relief='raised')  # Re-enable all resolution buttons
        self.update_window_title()

    # Function to disconnect the camera
    def disconnect_camera(self):
        self.cam.Close()
        self.update_window_title()

    # Function to toggle play/stop
    def toggle_play_stop(self):
        self.play = not self.play

    # Function to toggle red cross
    def toggle_red_cross(self):
        self.red_cross = not self.red_cross

    def toggle_my_proc(self):
        self.my_proc = not self.my_proc

    # Function to change frame size
    def change_frame_size(self, size):
        width, height = map(int, size.split('x'))
        ret = self.cam.SetResolution(width, height)
        if ret:
            #print(f"Resolution changed to {size}.")
            self.current_resolution = size
            self.update_button_styles()
            # TODO: update offsets and zooms 
            # height, width, _ = self.frame_shape
            scale_x = width / self.frame_shape[1]
            scale_y = height / self.frame_shape[0]
            #print("scaling: ", scale_x, scale_y)
            self.offset_x *= scale_x
            self.offset_y *= scale_y
        else:
            self.resolution_buttons[size].config(state='disabled')  # Disable unsupported resolution
            #print(f"Resolution {size} not supported.")

    # Function to update button styles
    def update_button_styles(self):
        for res, btn in self.resolution_buttons.items():
            if res == self.current_resolution:
                btn.config(relief='sunken')
            else:
                btn.config(relief='raised')

    # Function to toggle recording
    def toggle_recording(self):
        self.recording = not self.recording
        if self.recording:
            # Start recording
            try:
                now = datetime.now()
                filename = now.strftime("video_%Y-%m-%d_%H%M%S") + f".{self.video_ext}"
                filepath = os.path.join(self.record_folder, filename)
                fps = self.cam.GetFPS() if not self.initial_fps else self.initial_fps
                
                height, width, _ = self.frame_shape
                self.video_writer = cv2.VideoWriter(filepath, self.video_fourcc, fps, (width, height))
                self.btn_record.config(text="Stop", fg="red")
                print("recording into file: ", filepath)
            except Exception as e:
                print("creating video file exception: ", str(e), ", file name: ", filepath)
                self.btn_record.config(state='disabled') 
        else:
            # Stop recording
            self.video_writer.release()
            self.video_writer = None
            self.btn_record.config(text="Start", fg="red")

    def take_snapshot(self):
        self.snap_next = True  # just setting the flag
  
    def update_window_title(self):
        self.window.title(f"Camera({self.cam.GetId() if self.cam else '?'}) zoom: {self.zoom_factor:.2f}")

    def zoom_in(self, event=None):
        #nonlocal offset_x, offset_y, zoom_factor, frame_shape
        self.zoom_factor *= self.zoom_scale
        if self.verbose: print("zoom in: ", self.zoom_factor)
    
        height, width, _ = self.frame_shape
        if event is not None:
            x, y = (event.x, event.y)
        else:
            x, y = width/2, height/2
            
        # Calculate relative position of the event point within the current view
        self.offset_x += x * (self.zoom_scale -1) / self.image_zoom / self.zoom_factor
        self.offset_y += y * (self.zoom_scale -1) / self.image_zoom / self.zoom_factor

        # Ensuring offsets do not go out of bounds
        self.offset_x = max(min(self.offset_x, width - width / self.zoom_factor), 0)
        self.offset_y = max(min(self.offset_y, height - height / self.zoom_factor), 0)
        self.update_window_title()
        
    def reset_zoom(self, event=None):
        if self.verbose: print("zoom reset")
        #nonlocal  zoom_factor, offset_x, offset_y
        self.zoom_factor, self.offset_x, self.offset_y = 1.0, 0, 0
        self.update_window_title()

    def zoom_out(self, event=None):
        #nonlocal  offset_x, offset_y, zoom_factor, frame_shape
        self.zoom_factor = max(self.zoom_factor/self.zoom_scale, 1.0)
        if self.verbose: print("zoom out: ", self.zoom_factor)
        
        # adjusting offsets if needed, so that visible rect stays within the frame
        # bottom right is: (offset_y + height/zoom_factor), (offset_x + width/zoom_factor)
        height, width, _ = self.frame_shape
        if event is not None:
            x, y = (event.x, event.y)
        else:
            x, y = width/2, height/2
            
        # Calculate relative position of the event point within the current view
        self.offset_x -= x * (1-1/self.zoom_scale) / self.image_zoom / self.zoom_factor
        self.offset_y -= y * (1-1/self.zoom_scale) / self.image_zoom / self.zoom_factor

        # Ensuring offsets do not go out of bounds
        self.offset_x = max(min(self.offset_x, width - width / self.zoom_factor), 0)
        self.offset_y = max(min(self.offset_y, height - height / self.zoom_factor), 0)
        self.update_window_title()

    def zoom_change(self, event=None):
        if self.verbose: print("zoom click")
        if not event:
            return
        button_width = self.btn_zoom.winfo_width()

        # Determine the button area clicked
        if event.x < button_width / 3:
            self.zoom_out()  # Left third
        elif event.x > 2 * button_width / 3:
            self.zoom_in()  # Right third
        else:
            self.reset_zoom()  # Middle third


    def on_mouse_wheel(self, event):
        # Adjust zoom factor based on mouse wheel movement
        if event.num == 5 or event.delta == -120:  # Scroll down or equivalent
            self.zoom_out(event)
        elif event.num == 4 or event.delta == 120:  # Scroll up or equivalent
            self.zoom_in(event)
            
    def mouse_start_scroll(self, event):
        #nonlocal prev_x, prev_y, scroll_path, zoom_factor
        if self.verbose: print("start scroll:", ((event.x, event.y) if event else "None"), ", zoom: ", self.zoom_factor)
        self.prev_x = event.x
        self.prev_y = event.y
        self.scroll_path = None

    def mouse_scroll(self, event):
        #print("mouse scroll:", ((event.x, event.y) if event else "None"))
        #nonlocal prev_x, prev_y, offset_x, offset_y, zoom_factor, frame_shape
        #nonlocal scroll_path, image_zoom 
        
        # tracking path to detect it was click or scroll
        if self.scroll_path == None:   
            self.scroll_path = 0
        self.scroll_path += abs(self.prev_x - event.x) + abs(self.prev_y - event.y)

        self.offset_x += (self.prev_x - event.x) / self.image_zoom / (self.zoom_factor if self.sticky_scroll else 1)
        self.offset_y += (self.prev_y - event.y) / self.image_zoom / (self.zoom_factor if self.sticky_scroll else 1)
        self.prev_x = event.x
        self.prev_y = event.y
        
        # fitting into frame
        if self.offset_x < 0:  
            self.offset_x = 0
        if self.offset_y < 0:  
            self.offset_y = 0
        height0, width0, _ = self.frame_shape
        height = height0 / self.zoom_factor
        width  = width0 / self.zoom_factor
        
        if self.offset_x + width > width0:
            self.offset_x = width0 - width
        if self.offset_y + height > height0:
            self.offset_y = height0 - height

    def mouse_end_click(self, event):
        if not self.scroll_path or self.scroll_path < 10:
            self.handle_click(event, "click")

    # Function to handle mouse click on the video
    def handle_click(self, event, click_type):
        if self.verbose: print("click", click_type)
        #global  me_pos
        # Calculate click position relative to the scaled, zoomed, shifted frame
        try:
            # transformation is: shift, user-zoom, window-zoom
            #    reverse is : unzoom, unzoom, shift-back
            
            # external params: zoom_factor, offset_x, offset_y
            # window-zoom factors, should be the same actually
            cam_width, cam_height = self.cam.GetResolution()
            scale_w = self.label.winfo_width() / cam_width
            scale_h = self.label.winfo_height() / cam_height
            
            x, y = event.x, event.y  # in window's coordinates
            x, y = int(x / scale_w), int(y / scale_h)  # window unzoom
            x, y = int(x / self.zoom_factor), int(y / self.zoom_factor)  # user unzoom
            x, y = int(x + self.offset_x), int(y + self.offset_y)  # user shift-back

        except Exception as e:
            print("exception: ", str(e))
            return
        if self.verbose: print(f"{self.click_type}: ({x}, {y})")
        if click_type == "double":
            #nonlocal full_screen
            self.full_screen = not self.full_screen
            self.window.attributes("-fullscreen", self.full_screen)
        else:
            self.me_pos = (x/self.frame_shape[1], y/self.frame_shape[0])  # making relative
    
def display_help():
    help_message = f"""
    Usage: python your_script.py [options] [resolutions...]
    
    Options:
    --help, /?      Show this help message and exit
    cam=<index>     Specify the camera index (default is {default_camera_index})
    fps=<fps>       Recording's frames-per-second (default is same as cam's video)
    path=<folder>   Specify output path. folder will be created if needed
                        (default is {record_folder})
    codec=<fourcc>  Encoder for video recording, can be X264, H264, AVC1, MJPG, XVID,
                        whatever is supported in your system (default is {codec_str})
    vid=<ext>       Video container's format for recording, like mp4, avi
                        (defaul is {video_ext})
    img=<ext>       Image snapshot's format, like jpg, png, tiff
                        (defailt is {image_ext})
    mouse can be used to zoom in/out and to scroll around
    
    Resolutions:
    Specify resolutions as WIDTHxHEIGHT. Prefix with '+' to set as initial resolution.
        (default resolutions are: {default_resolutions})
    
    Examples:
    python your_script.py 800x600 +1024x768 1280x720
    python your_script.py cam=1 +1920x1080 1280x720 path=./snaps
    """
    print(help_message)

def main():
    global  default_camera_index, initial_fps, record_folder, video_fourcc
    global  codec_str, video_ext, image_ext
    # if help requested just print and exit
    if '--help' in sys.argv or '/?' in sys.argv:
        display_help()
        sys.exit()
        
    # Default common resolutions and camera index
    initial_resolution = None
    custom_resolutions = []
    camera_index = default_camera_index  # Default camera index

    # Parse command line arguments
    for arg in sys.argv[1:]:
        if arg.startswith('+'):
            initial_resolution = arg[1:]
            custom_resolutions.append(initial_resolution)
        elif arg.startswith('cam='):
            id_strs = arg.split('=')[1].split(',')
            camera_index = [int(s) for s in id_strs]
        elif arg.startswith('path='):
            record_folder = arg.split('=')[1]
        elif arg.startswith('fps='):
            initial_fps = float(arg.split('=')[1])            
        elif arg.startswith('codec='):
            codec_str = arg.split('=')[1]
            video_fourcc = cv2.VideoWriter_fourcc(*codec_str)
        elif arg.startswith('vid='):
            video_ext = arg.split('=')[1]            
        elif arg.startswith('img='):
            image_ext = arg.split('=')[1]            
        else:
            custom_resolutions.append(arg)

    # Check if the camera is available
    camera_found = None
    """
    print("Checking camera ", end='', flush=True)
    # Set the logging level to suppress warnings
    while not camera_found:
        for id in camera_index:
            if CameraCV2.check_camera(id):
                camera_found = id
                break
            print(".", end='', flush=True)
        if not camera_found:
            time.sleep(1)
    print(" camera found:", camera_found)
    #"""

    # Determine the list of resolutions and initial resolution
    if custom_resolutions:
        if not initial_resolution:
            initial_resolution = custom_resolutions[0]
    else:
        custom_resolutions = default_resolutions
        initial_resolution = None  #default_resolutions[0]

    # Remove duplicates and sort the resolutions
    custom_resolutions = sorted(set(custom_resolutions), key=lambda x: (int(x.split('x')[0]), int(x.split('x')[1])))

    cam = CameraCV2(camera_index, start=True)
    if not cam.IsOpen():
        print(" camera not found, id(s) checked: ", camera_index)
    play = CamPlay(cam=cam, cam_id=camera_found, 
                   resolutions=custom_resolutions, initial_res=initial_resolution)
    play.run()

    #display_camera(camera_index, initial_resolution, custom_resolutions)
    
if __name__ == "__main__":
    main()
