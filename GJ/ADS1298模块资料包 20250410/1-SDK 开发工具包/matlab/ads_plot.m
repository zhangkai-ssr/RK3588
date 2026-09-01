classdef ads_plot < handle

    properties
        isExitCollect = 0;
        plotData = [];
        plot_chx = [];
    end

    methods

        function obj = ads_plot()
             figure('Name','Data','NumberTitle','off','menubar','none','toolbar','none','CloseRequestFcn',@obj.emgFigure_closereq);
             % obj.plotData = plot(1:1);   
             hold on
             for ch=1:32
                 obj.plot_chx{ch} = plot(1:1);
             end
             hold off
        end

        function emgFigure_closereq(obj,src,event)
             if obj.isExitCollect == 0
                 obj.isExitCollect = 1; 
                 delete(src)     
             end  
        end
 
        function plot(obj,data,winLen)
            if obj.isExitCollect == 0    
                len = length(data); 
                if (len <= winLen)
                    plot(data);
                else
                    x = (len-winLen):len;
                    plot(x,data(x));
                    xlim([(len-winLen) len]);
                end
            end
        end

        function plot_data(obj,dataPlot,data,winLen)
           p = dataPlot;
           if obj.isExitCollect == 0
            len = length(data);
            if (len <= winLen)
                p.XData = 1:len;
                p.YData = data;
            else
                x = (len-winLen+1):len;
                % p.XData = x;
                p.XData = 1:winLen;
                p.YData = data(x);

                % xlim([(len-winLen) len]);
                % x = 1:length(data);
                % p.XData = x;
                % p.YData = data(x);
            end
           end
        end

        function plot_chx_data(obj,ch,data,winLen)
             plot_data(obj,obj.plot_chx{ch},data,winLen);
             % ylim([-500 500]);

             % 测试代码
             % len = length(w2Data(1).rawData);
             % winLen = 5000;
             % if len>winLen
             %     xlim([(len-winLen) len]);
             % end
        end

    end
end