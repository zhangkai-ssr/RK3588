classdef ads_cmd  
    
    properties (Constant)   % 定义类常量
       ADDRESS_BOARD         = 0x01     % 硬件版本
       ADDRESS_SOFTWARE      = 0x02     % 软件版本
       ADDRESS_LH001_LOFF    = 0x08     % 导联脱落
       ADDRESS_EMG_START = 0x11
    end
    
    properties   %定义属性－－－类变量
        % Value {mustBeNumeric}
    end
    
    methods

        % 指令打包
        function cmd = cmdDataPack(obj,address,isWrite,data)
           
           cmd = [];

           cmd(1) = 0xAA;
           cmd(2) = length(data) + 3;

           if isWrite == 0
               cmd(3) = 0x81;
           else
               cmd(3) = 0x80;
           end

           cmd(4) = address;

           cmd = [cmd data];

            xor = 0;
            for i=2:length(cmd)
               xor = bitxor(xor,cmd(i)); 
            end

            cmd = [cmd xor 0xBB];
        end

        % 读取硬件版本
        function cmd = readHardwareVersion(obj)
            cmd = cmdDataPack(obj,obj.ADDRESS_BOARD,0,[]);
        end

        % 读取软件版本
        function cmd = readSowftware(obj)
            cmd = cmdDataPack(obj,obj.ADDRESS_SOFTWARE,0,[]);
        end

        % 开始采集肌电信号
        function cmd = startCollectCmd(obj)
           data = [];
           data(1) = 0x03;
           data(2:9) = 0;
           cmd = cmdDataPack(obj,obj.ADDRESS_EMG_START,1,data);
        end

        % 停止采集
        function cmd = stopCollectCmd(obj)
           data = [];
           data(1) = 0x00;
           data(2:9) = 0;
           cmd = cmdDataPack(obj,obj.ADDRESS_EMG_START,1,data);
        end
    end
end

