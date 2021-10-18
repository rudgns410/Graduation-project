import argparse
from sys import platform

from models import *  # set ONNX_EXPORT in models.py
from utils.datasets import *
from utils.utils import *
from utils.audio_utils import *
import os


def detect(save_img=False):
    img_size = (320, 192) if ONNX_EXPORT else opt.img_size  # (320, 192) or (416, 256) or (608, 352) for (height, width)
    out, source, weights, half, view_img, save_txt = opt.output, opt.source, opt.weights, opt.half, opt.view_img, opt.save_txt

    device = torch_utils.select_device(device='cpu' if ONNX_EXPORT else opt.device)
    if not os.path.exists(out):
        os.makedirs(out)  # make new output folder

    model = Darknet(opt.cfg, img_size)

    attempt_download(weights)
    if weights.endswith('.pt'):  # pytorch format
        model.load_state_dict(torch.load(weights, map_location=device)['model'])
    else:
        load_darknet_weights(model, weights)


    model.to(device).eval()

    if ONNX_EXPORT:
        model.fuse()
        img = torch.zeros((1, 3) + img_size)  # (1, 3, 320, 192)
        f = opt.weights.replace(opt.weights.split('.')[-1], 'onnx')  # *.onnx filename
        torch.onnx.export(model, img, f, verbose=False, opset_version=11)

        import onnx
        model = onnx.load(f)  # Load the ONNX model
        onnx.checker.check_model(model)  # Check that the IR is well formed
        print(onnx.helper.printable_graph(model.graph))  # Print a human readable representation of the graph
        return

    half = half and device.type != 'cpu'  # half precision only supported on CUDA
    if half:
        model.half()

    vid_path, vid_writer = None, None
    save_img = True
    dataset = LoadImages(source, img_size=img_size)

    names = load_classes(opt.names)
    colors = [[random.randint(0, 255) for _ in range(3)] for _ in range(len(names))]

    t0 = time.time()
    temp_img_list = []
    xyxy_list = []
    for path, img, im0s, vid_cap in dataset:
        img = torch.from_numpy(img).to(device)
        img = img.half() if half else img.float()  # uint8 to fp16/32
        img /= 255.0  # 0 - 255 to 0.0 - 1.0
        if img.ndimension() == 3:
            img = img.unsqueeze(0)

        t1 = torch_utils.time_synchronized()
        pred = model(img)[0].float() if half else model(img)[0]
        t2 = torch_utils.time_synchronized()

        pred = non_max_suppression(pred, opt.conf_thres, opt.iou_thres, classes=opt.classes, agnostic=opt.agnostic_nms)

        if len(temp_img_list) < 30:
            temp_img_list.append(im0s)
        else:
            temp_img_list.pop(0)
            temp_img_list.append(im0s)
        xyxy_temp_list = []
        for i, det in enumerate(pred):  # detections per image
            p, s, im0 = path, '', im0s
            save_path = str(Path(out) / Path(p).name)
            s += '%gx%g ' % img.shape[2:]  # print string
            if det is not None and len(det):
                det[:, :4] = scale_coords(img.shape[2:], det[:, :4], im0.shape).round()

                for c in det[:, -1].unique():
                    n = (det[:, -1] == c).sum()  # detections per class
                    s += '%g %ss, ' % (n, names[int(c)])  # add to string

                for *xyxy, conf, cls in det:
                    if save_txt:  # Write to file
                        with open(save_path + '.txt', 'a') as file:
                            file.write(('%g ' * 6 + '\n') % (*xyxy, cls, conf))

                    if save_img or view_img:  # Add bbox to image
                        mosaic_one_box(xyxy, im0)
                        xyxy_temp_list.append(xyxy)
                        st = check_xyxy_list(xyxy, xyxy_list)
                        if st > 0:
                            for i in range(st, len(xyxy_list)):
                                mosaic_one_box(xyxy, temp_img_list[i])


            if view_img:
                cv2.imshow(p, im0)
                if cv2.waitKey(1) == ord('q'):  # q to quit
                    raise StopIteration

            if save_img:
                if dataset.mode == 'images':
                    cv2.imwrite(save_path, im0)
                else:
                    if vid_path != save_path:  # new video
                        vid_path = save_path
                        if isinstance(vid_writer, cv2.VideoWriter):
                            vid_writer.release()  # release previous video writer

                        fps = vid_cap.get(cv2.CAP_PROP_FPS)
                        w = int(vid_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        h = int(vid_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        vid_writer = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc(*opt.fourcc), fps, (w, h))
                    if len(temp_img_list) >= 30:
                        vid_writer.write(temp_img_list[0])
        if len(xyxy_list) < 30:
            xyxy_list.append(xyxy_temp_list)
        else:
            xyxy_list.pop(0)
            xyxy_list.append(xyxy_temp_list)
    while temp_img_list:
        vid_writer.write(temp_img_list.pop(0))
    # Add audio to results
    if isinstance(vid_writer, cv2.VideoWriter):
        vid_writer.release()
        add_audio(source, out)

    if save_txt or save_img:
        if platform == 'darwin':  # MacOS
            os.system('open ' + out + ' ' + save_path)

    print('Done. (%.3fs)' % (time.time() - t0))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cfg', type=str, default='cfg/yolov3-spp-3cls-custom.cfg', help='*.cfg path')
    parser.add_argument('--names', type=str, default='data/inapp_obj.names', help='*.names path')
    parser.add_argument('--weights', type=str, default='weights/best.pt', help='weights path')
    parser.add_argument('--source', type=str, default='data/samples', help='source')  # input file/folder
    parser.add_argument('--output', type=str, default='output', help='output folder')  # output folder
    parser.add_argument('--img-size', type=int, default=512, help='inference size (pixels)')
    parser.add_argument('--conf-thres', type=float, default=0.3, help='object confidence threshold')
    parser.add_argument('--iou-thres', type=float, default=0.4, help='IOU threshold for NMS')
    parser.add_argument('--fourcc', type=str, default='mp4v', help='output video codec (verify ffmpeg support)')
    parser.add_argument('--half', action='store_true', help='half precision FP16 inference')
    parser.add_argument('--device', default='', help='device id (i.e. 0 or 0,1) or cpu')
    parser.add_argument('--view-img', action='store_true', help='display results')
    parser.add_argument('--save-txt', action='store_true', help='save results to *.txt')
    parser.add_argument('--classes', nargs='+', type=int, help='filter by class')
    parser.add_argument('--agnostic-nms', action='store_true', help='class-agnostic NMS')
    opt = parser.parse_args()

    with torch.no_grad():
        detect()
