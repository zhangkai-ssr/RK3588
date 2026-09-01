function  ryty_fft(fs,x)
 
    %Fs = 1000;            % 采样率                    
    L = length(x);        % 信号长度
     
    % 计算信号的傅里叶变换
    Y = fft(x);     
    
    % 计算双侧频谱 P2
    P2 = abs(Y/L);
    
    % 基于 P2 和偶数信号长度 L 计算单侧频谱 P1。
    P1 = P2(1:L/2+1);    
    P1(2:end-1) = 2*P1(2:end-1);
    
    % 绘制单侧频谱 P1
    f = fs*(0:(L/2))/L;
    plot(f,P1) 
    title('Single-Sided Amplitude Spectrum of X(t)')
    xlabel('f (Hz)')
    ylabel('|P1(f)|')
end

