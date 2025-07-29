% DeepFRET MATLAB classification example
%
% This script demonstrates how to load the pre-trained Keras models shipped
% with DeepFRET and perform classification of FRET traces directly in
% MATLAB. It mirrors the main steps performed by the Python GUI:
%   1. Correct intensities for cross-talk
%   2. Normalize each trace
%   3. Run the neural network to obtain per-frame probabilities
%   4. Aggregate probabilities to obtain a final class and confidence
%
% The script expects a variable 'trace' which contains the raw intensity
% arrays in the following order (same as the Python code):
%   1. Donor intensity    (Dexc-Dem)
%   2. Donor background   (Dexc-Dem bg)
%   3. Acceptor intensity (Dexc-Aem)
%   4. Acceptor background(Dexc-Aem bg)
%   5. Red intensity      (Aexc-Aem)
%   6. Red background     (Aexc-Aem bg)
%
% See README for details on trace formatting.

%% Model loading
% Point to the location of the .h5 models that ship with DeepFRET. These
% files are found under `src/main/python/resources/` in the repository.
model2CPath = fullfile('src','main','python','resources','FRET_2C_keras_model.h5');
model3CPath = fullfile('src','main','python','resources','FRET_3C_keras_model.h5');

% Import the networks using MATLAB's Deep Learning Toolbox
net2C = importKerasNetwork(model2CPath, 'OutputLayerType','classification');
net3C = importKerasNetwork(model3CPath, 'OutputLayerType','classification');

%% Intensity correction helper
function [F_DA, I_DD, I_DA, I_AA] = correct_DA(intensities, alpha, delta)
    grn_int = intensities{1};
    grn_bg  = intensities{2};
    acc_int = intensities{3};
    acc_bg  = intensities{4};
    red_int = intensities{5};
    red_bg  = intensities{6};

    I_DD = grn_int - grn_bg;
    I_DA = acc_int - acc_bg;
    I_AA = red_int - red_bg;

    if any(isnan(I_AA))
        F_DA = I_DA - alpha .* I_DD;
    else
        F_DA = I_DA - alpha .* I_DD - delta .* I_AA;
    end
end

%% Sample-wise max normalisation
function Xn = sample_max_normalize_3d(X)
    if ndims(X) == 2
        X = reshape(X,1,size(X,1),size(X,2));
    end
    arr_max = max(X,[],[2 3]);
    Xn = X ./ arr_max;
end

%% Find bleaching frame based on probability column
function bleachFrame = find_bleach(p_bleach, threshold, window)
    if nargin < 2, threshold = 0.5; end
    if nargin < 3, window = 7; end
    is_bleached = medfilt(double(p_bleach > threshold), window);
    bleachFrame = find(is_bleached,1,'first');
    if isempty(bleachFrame)
        bleachFrame = [];
    elseif all(is_bleached)
        bleachFrame = 1;
    end
end

%% Aggregate per-frame probabilities
function [p, confidence, bleachFrame] = seq_probabilities(yi, skip_threshold, min_frames)
    if nargin < 2, skip_threshold = 0.5; end
    if nargin < 3, min_frames = 5; end
    bleachFrame = find_bleach(yi(:,1), skip_threshold);

    valid = yi(yi(:,1) < skip_threshold, :);
    if isempty(bleachFrame) || bleachFrame > min_frames
        p = sum(valid,1) ./ size(valid,1);
        p = p ./ sum(p);
    else
        p = zeros(1,size(yi,2));
        p(1) = 1;
    end
    confidence = sum(p(5:end));
end

%% Classification function
function [traceClass, confidence] = classify_trace(intensities, alpha, delta, net2C, net3C)
    [F_DA, I_DD, ~, I_AA] = correct_DA(intensities, alpha, delta);
    xi = [F_DA; I_DD; I_AA]';

    hasRed = ~any(isnan(I_AA));
    if hasRed
        model = net3C;
        xi = xi(:,[2 3 1]); % MATLAB uses (time,features)
    else
        model = net2C;
        xi = xi(:,[2 3]);
    end

    xi = sample_max_normalize_3d(xi);
    yi = predict(model, xi);
    [p, confidence, ~] = seq_probabilities(yi);
    [~, idx] = max(p);
    classes = {"bleached","aggregated","noisy","scrambled","1-state", ...
               "2-state","3-state","4-state","5-state"};
    traceClass = classes{idx};
end

% Example usage (requires variable 'trace' with intensities)
% alpha = 0; delta = 0;
% [cls, conf] = classify_trace(trace, alpha, delta, net2C, net3C);
% fprintf('Predicted class: %s (confidence %.2f)\n', cls, conf);
