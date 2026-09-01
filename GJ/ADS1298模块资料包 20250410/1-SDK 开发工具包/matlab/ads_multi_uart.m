clc
clear
close all

% 滤波系数
load('filters_hd.mat')

% 绘图
adsPlot = ads_plot;

% 指令集
adsCmd = ads_cmd;

% 串口号列表
ports ={'COM53'};

% 设备数量
device_num = length(ports);

for i=1:device_num
   
   % 串口对象
   uarts(i) = serialport(ports{i},1000000);
   configureCallback(uarts(i),"off");

   % 数据集
   adsData(i) = ads_data;
   adsData(i).hd_highpass_20hz = Hd_HighPass_20Hz; % 高通滤波器系数
   adsData(i).hd_comb_50hz = Hd_Comb_50Hz; % 50Hz梳状态滤波器系数
end

% 停止采集
uarts_send_cmd(uarts,adsCmd.stopCollectCmd());
pause(0.5)

disp('开始采集');
uarts_send_cmd(uarts,adsCmd.startCollectCmd());

% 等待数据接收
while(adsPlot.isExitCollect == 0)
    pause(0.2);
    
    % 读取串口数据并解析
    uarts_read_parse(uarts,adsData);

    % 更新绘图
    for i=1:device_num
        chx_data = adsData(i).chx_val;
        if ~isempty(chx_data)
           winLen = 2500;
           for ch =1:8
               adsPlot.plot_chx_data((i-1)*8+ch,chx_data(:,ch) + ((i-1)*8+ch)*1000,winLen);
           end
        end
    end
end

% 停止采集
uarts_send_cmd(uarts,adsCmd.stopCollectCmd());
pause(0.5)

% 关闭串口
for i=1:device_num
   delete(uarts(i))
end

% 绘制曲线图
hold on
    for i=1:device_num
        chx_val = adsData(i).chx_val;
        if ~isempty(chx_val)
            for ch = 1:8
               plot(chx_val(:,ch) + ch*1000) 
            end
        end
    end
hold off

% 通过串口向设备发送指令
function uarts_send_cmd(uarts,cmd)
   for i=1:length(uarts)
        write(uarts(i),cmd,"uint8");
   end
end

% 串口数据读取并解析
function uarts_read_parse(uarts,adsdata)
    for i=1:length(uarts)
        if uarts(i).NumBytesAvailable > 0
            dataRev = read(uarts(i),uarts(i).NumBytesAvailable,"uint8");
            adsdata(i).dataUnpack(dataRev);
        end
    end
end



