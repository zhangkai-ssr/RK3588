classdef ads_data <handle

    properties

      dataCache = [];    
      rawData =[];

      softwareVersion = []; % 软件版本
      hardwareVersion = ""; % 硬件版本

      frame_number = 0; % 数据帧序号
      chx_val = [];

      % 高通滤波器
      hd_highpass_20hz = [];
      h_zf = cell(8,1);

      % 50Hz陷波器
      hd_comb_50hz = [];
      comb_zf = cell(8,1); 

    end
    
    methods
           
        % 数据包解析
        function dataUnpack(obj,data_in)

           data = [obj.dataCache data_in];
           dataLen = uint64(length(data));
           addr_n = uint64(1); %解包地址计数
     
           while ((dataLen - addr_n) > 5)
        
                %校验字节
                checkByte = bitxor(data(addr_n+1),data(addr_n+2)); 
        
                    %帧头校验
                    if((data(addr_n)== 0xA5) && data(addr_n+3) == checkByte)
        
                        %帧长度
                        frameLen = uint64(data(addr_n+1) + 3);
        
                        % 校验长度
                        if(frameLen <= (dataLen - addr_n +1))
      
                            % 校验帧尾
                            if ((data(addr_n + frameLen - 1)) == 0x5A)
                                frameUnpack(obj,data(addr_n:(addr_n+frameLen-1)));
                                addr_n = addr_n + frameLen;
                            else
                                disp("帧尾出错")
                                addr_n = addr_n +1;
                            end
                        else
                            % disp("数据长度不足")
                            break;
                        end
                    else 
                         disp("帧头校验出错")
                         addr_n = addr_n +1;
                    end
           end
        
           obj.dataCache = [];
           obj.dataCache = data(addr_n:dataLen);          
        end


        %数据帧解析
        function frameUnpack(obj,frame) 
            
            %帧地址/类型
            frame_type = frame(3);

%           t = datetime('now','Format','HH:mm:ss.SSS');
            switch (frame_type) 

                case ads_cmd.ADDRESS_BOARD
                    frameHardware(obj,frame);

                case ads_cmd.ADDRESS_SOFTWARE
                    frameSoftware(obj,frame);
                    
                case ads_cmd.ADDRESS_EMG_START
                     frameEmgRaw(obj,frame);         
            end
        end
        
        % 硬件版本解析帧
        function frameHardware(obj,frame) 
              len = frame(2) -2;
              obj.hardwareVersion = char(frame(5:5+len-1));
              disp("硬件版本号：" + obj.hardwareVersion);
        end

        % 软件版本解析帧
        function frameSoftware(obj,frame) 
            len = frame(2) -2;
            obj.softwareVersion = char(frame(5:5+len-1));
            disp("软件版本号：" + obj.softwareVersion);
        end

        % 原始数据解析帧 
        function frameEmgRaw(obj,frame)
            
            n = (frame(2) - 2)/4;
            val = typecast(cast(frame(5:(5+n*4-1)),"uint8"), 'single');
            val = double(val);
            
            chx_val_temp = [];
            for i=1:(n/8)
               index = (i-1)*8+1;
               chx_val_temp = [chx_val_temp;val(index:index+7)];
            end

            % 数据滤波
            h_den = obj.hd_highpass_20hz.Denominator;
            h_num = obj.hd_highpass_20hz.Numerator;
            c_den = obj.hd_comb_50hz.Denominator;
            c_num = obj.hd_comb_50hz.Numerator;
            for ch=1:8
              zf = cell2mat(obj.h_zf(ch));
              [chx_val_temp(:,ch),zf] = filter(h_num,h_den,chx_val_temp(:,ch),zf);
              obj.h_zf(ch) = {zf};

              zf = cell2mat(obj.comb_zf(ch));
              [chx_val_temp(:,ch),zf] = filter(c_num,c_den,chx_val_temp(:,ch),zf);
              obj.comb_zf(ch) = {zf};
            end

            % 数据缓存
            obj.chx_val = [obj.chx_val;chx_val_temp];
        end
       
    end
end

