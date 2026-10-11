%% generate_report_figures.m
% Generate MATLAB figures for the LingBot-MAP one-page report.
%
% Usage in MATLAB:
%   cd('/media/ee303/1tb/lingbot_map')
%   run('Integrated_version/docs/reports/report_benchmark_20260926T112228Z/matlab_figures/generate_report_figures.m')
%
% This script reads existing benchmark CSV/JSON files only. It does not rerun
% experiments and does not invent frame-level data.

clear; clc;

reportDir = fullfile('Integrated_version','docs','reports','report_benchmark_20260926T112228Z');
outDir = fullfile(reportDir, 'matlab_figures', datestr(now, 'yyyymmdd_HHMMSS'));
if ~exist(outDir, 'dir')
    mkdir(outDir);
end

mapGrowth = readtable(fullfile(reportDir, 'map_growth.csv'));
latencyByStage = readtable(fullfile(reportDir, 'latency_by_stage.csv'));
pipelineSummary = readtable(fullfile(reportDir, 'pipeline_summary.csv'), 'TextType', 'string');
orbSummary = jsondecode(fileread(fullfile(reportDir, 'orb_localization_summary.json')));
rtspSummary = jsondecode(fileread(fullfile(reportDir, 'rtsp_summary.json')));
unitTestText = fileread(fullfile(reportDir, 'unit_test_output.txt'));

unitTokens = regexp(unitTestText, 'Ran\s+(\d+)\s+tests?', 'tokens', 'once');
if ~isempty(unitTokens) && contains(unitTestText, 'OK')
    unitTestsResult = sprintf('%s tests OK', unitTokens{1});
else
    unitTestsResult = 'NOT VERIFIED';
end

predictionLongRow = pipelineSummary(pipelineSummary.pipeline == "prediction_long300", :);
lingbotFastRows = latencyByStage(string(latencyByStage.pipeline) == "lingbot_persistent_fast", :);
fastWindow2Row = latencyByStage(string(latencyByStage.pipeline) == "lingbot_persistent_fast" & string(latencyByStage.window) == "10-19", :);
modelLoadSeconds = mean(unique(latencyByStage.session_model_load_ms)) / 1000.0;

predictionUpdatesResult = sprintf('%d map updates', predictionLongRow.updates(1));
predictionEvidenceResult = sprintf('%d updates from existing world\_points', predictionLongRow.updates(1));
finalVoxelResult = formatInteger(predictionLongRow.final_voxel_count(1));
predictionLatencyResult = sprintf('mean %.3f ms', predictionLongRow.mean_latency_ms(1));
persistentModelLoadResult = sprintf('about %.1f s, session-level', modelLoadSeconds);
fastPathWindow2Result = sprintf('about %.1f s', fastWindow2Row.backend_total_ms(1) / 1000.0);
lingbotEvidenceResult = sprintf('%d-window profiling; windowed inference', height(lingbotFastRows));
orbReplayResult = sprintf('%d/%d localized; mean confidence %.4f', ...
    orbSummary.video_replay.localized_frames, ...
    orbSummary.video_replay.processed_frames, ...
    orbSummary.video_replay.mean_confidence);
orbEvidenceResult = sprintf('same-scene %d/%d accepted', ...
    orbSummary.video_replay.localized_frames, ...
    orbSummary.video_replay.processed_frames);
if isfield(rtspSummary, 'camera_connection') && rtspSummary.camera_connection && rtspSummary.frame_read
    rtspResult = 'VERIFIED';
else
    rtspResult = 'NOT VERIFIED in report run';
end

fprintf('Output directory: %s\n', outDir);

%% Figure 1: Architecture + evidence scope
fig = figure('Color','w','Position',[100 100 1500 620]);
clf(fig);

% Left panel: architecture branches
ax1 = axes('Position',[0.04 0.12 0.56 0.78]);
axis(ax1, [0 1 0 1]); axis(ax1, 'off'); hold(ax1, 'on');
title(ax1, 'Figure 1A. Target Runtime Branches', 'FontWeight','bold');

boxStyle = {'Curvature',0.08,'LineWidth',1.2};
blue = [0.93 0.97 1.00]; blueEdge = [0.17 0.37 0.54];
purple = [0.95 0.94 1.00]; purpleEdge = [0.40 0.31 0.64];
yellow = [1.00 0.97 0.90]; yellowEdge = [0.65 0.41 0.00];

bInput = drawBox(ax1, [0.02 0.66 0.16 0.12], 'RTSP / video\nframes', blue, blueEdge, boxStyle);
bQueue = drawBox(ax1, [0.23 0.66 0.16 0.12], 'Latest-frame\nqueue', blue, blueEdge, boxStyle);
bLing = drawBox(ax1, [0.46 0.79 0.17 0.12], 'LingBot-MAP\nwindow worker', blue, blueEdge, boxStyle);
bVoxel = drawBox(ax1, [0.68 0.79 0.16 0.12], 'Voxel fusion\n/ live map', blue, blueEdge, boxStyle);
bFront = drawBox(ax1, [0.89 0.79 0.09 0.12], 'Frontend\nviewer', blue, blueEdge, boxStyle);
bRef = drawBox(ax1, [0.23 0.36 0.16 0.12], 'Existing\nreference map', purple, purpleEdge, boxStyle);
bOrb = drawBox(ax1, [0.46 0.50 0.17 0.12], 'ORB\nlocalization', purple, purpleEdge, boxStyle);
bPose = drawBox(ax1, [0.68 0.50 0.16 0.12], 'PoseGate', purple, purpleEdge, boxStyle);
bNav = drawBox(ax1, [0.68 0.28 0.16 0.12], 'Navigation\nPure Pursuit', purple, purpleEdge, boxStyle);
bCmd = drawBox(ax1, [0.89 0.28 0.09 0.12], 'Dry-run\ncommand log', yellow, yellowEdge, boxStyle);

drawArrow(ax1, bInput, bQueue, 'right-left');
drawArrow(ax1, bQueue, bLing, 'right-left');
drawArrow(ax1, bLing, bVoxel, 'right-left');
drawArrow(ax1, bVoxel, bFront, 'right-left');
drawArrow(ax1, bQueue, bOrb, 'right-left');
drawArrow(ax1, bRef, bOrb, 'right-left');
drawArrow(ax1, bOrb, bPose, 'right-left');
drawArrow(ax1, bPose, bNav, 'bottom-top');
drawArrow(ax1, bNav, bCmd, 'right-left');
text(ax1, 0.60, 0.95, 'Mapping branch', 'Color', blueEdge, 'FontWeight','bold', 'HorizontalAlignment','center');
text(ax1, 0.60, 0.44, 'Localization / navigation branch', 'Color', purpleEdge, 'FontWeight','bold', 'HorizontalAlignment','center');
text(ax1, 0.50, 0.05, 'No PoseGate/Navigation arrow points to voxel fusion. Reference map is an ORB input.', ...
    'HorizontalAlignment','center', 'FontSize',9, 'Color',[0.3 0.3 0.3]);

% Right panel: evidence scope
ax2 = axes('Position',[0.64 0.12 0.32 0.78]);
axis(ax2, [0 1 0 1]); axis(ax2, 'off'); hold(ax2, 'on');
title(ax2, 'Figure 1B. Evidence Scope', 'FontWeight','bold');
items = {
    'Unit tests', unitTestsResult, [0.91 0.97 0.92], [0.18 0.49 0.20];
    'Prediction replay', predictionEvidenceResult, [0.91 0.97 0.92], [0.18 0.49 0.20];
    'LingBot worker', lingbotEvidenceResult, [1.00 0.97 0.88], [0.70 0.42 0.00];
    'ORB replay', orbEvidenceResult, [0.91 0.97 0.92], [0.18 0.49 0.20];
    'RTSP live benchmark', rtspResult, [0.99 0.93 0.92], [0.70 0.15 0.12];
    'Physical accuracy', 'NOT AVAILABLE: no ground truth', [0.99 0.93 0.92], [0.70 0.15 0.12]
};
y = 0.80;
for i = 1:size(items,1)
    rectangle(ax2, 'Position',[0.05 y 0.90 0.10], 'FaceColor',items{i,3}, 'EdgeColor',items{i,4}, 'LineWidth',1.2, 'Curvature',0.08);
    text(ax2, 0.09, y+0.065, items{i,1}, 'FontWeight','bold', 'FontSize',10);
    text(ax2, 0.09, y+0.030, items{i,2}, 'FontSize',9, 'Interpreter','tex');
    y = y - 0.13;
end
text(ax2, 0.50, 0.05, 'Evidence blocks are independent findings, not one fully verified live pipeline.', ...
    'HorizontalAlignment','center', 'FontSize',9, 'Color',[0.3 0.3 0.3]);

saveReportFigure(fig, outDir, 'fig1_architecture_scope_matlab');

%% Figure 2: Map growth split panels
fig = figure('Color','w','Position',[100 100 950 760]);
tiledlayout(3,1,'TileSpacing','compact','Padding','loose');

nexttile;
plot(mapGrowth.update_index, mapGrowth.voxel_count, '-o', 'LineWidth',1.5, 'MarkerSize',3);
grid on; ylabel('Voxel count');
title('Figure 2. Prediction Replay Map Growth (34 updates)');

nexttile;
plot(mapGrowth.update_index, mapGrowth.fused_points, '-o', 'LineWidth',1.5, 'MarkerSize',3, 'Color',[0.18 0.55 0.18]);
grid on; ylabel('Fused points');

nexttile;
plot(mapGrowth.update_index, mapGrowth.output_bytes/1024, '-o', 'LineWidth',1.5, 'MarkerSize',3, 'Color',[0.78 0.16 0.16]);
grid on; xlabel('Map update index'); ylabel('Output size (KB)');
annotation(fig, 'textbox', [0.08 0.005 0.86 0.05], 'String', ...
    'Source: map\_growth.csv fields update\_index, voxel\_count, fused\_points, output\_bytes. Existing predictions.npz replay; not online RGB inference.', ...
    'EdgeColor','none', 'HorizontalAlignment','center', 'FontSize',8, 'Interpreter','tex');
saveReportFigure(fig, outDir, 'fig2_map_growth_matlab');

%% Figure 3: prediction_long300 latency
row = pipelineSummary(pipelineSummary.pipeline == "prediction_long300", :);
meanLatency = double(row.mean_latency_ms);
p50Latency = double(row.p50_latency_ms);
p95Latency = double(row.p95_latency_ms);

fig = figure('Color','w','Position',[100 100 950 540]);
plot(mapGrowth.update_index, mapGrowth.latency_ms, '-o', 'LineWidth',1.5, 'MarkerSize',3, 'DisplayName','update latency\_ms');
hold on; grid on;
yline(meanLatency, '-', sprintf('mean = %.3f ms', meanLatency), 'LineWidth',1.4, 'Color',[0.85 0.25 0.25], 'LabelHorizontalAlignment','left');
yline(p50Latency, '--', sprintf('p50 = %.3f ms', p50Latency), 'LineWidth',1.2, 'Color',[0.20 0.60 0.60], 'LabelHorizontalAlignment','left');
yline(p95Latency, ':', sprintf('p95 = %.3f ms', p95Latency), 'LineWidth',1.6, 'Color',[0.90 0.45 0.10], 'LabelHorizontalAlignment','left');
xlabel('Map update index'); ylabel('Latency (ms)');
title('Figure 3. prediction\_long300 Replay Latency');
legend('Location','best');
text(0.02, 0.96, sprintf('Source package: 43 frames\nObserved updates: 34\nMetric row: prediction\_long300 only'), ...
    'Units','normalized', 'VerticalAlignment','top', 'BackgroundColor','white', 'EdgeColor',[0.6 0.6 0.6], 'FontSize',8, 'Interpreter','tex');
annotation(fig, 'textbox', [0.08 0.005 0.86 0.05], 'String', ...
    'Source: map\_growth.csv latency\_ms + pipeline\_summary.csv prediction\_long300 row. Does not use prediction\_npz 361.842 ms.', ...
    'EdgeColor','none', 'HorizontalAlignment','center', 'FontSize',8, 'Interpreter','tex');
saveReportFigure(fig, outDir, 'fig3_prediction_long300_latency_matlab');

%% Figure 4: Persistent LingBot grouped stage and total latency
stageNames = {'image prepare','inference','archive write','point extract','fusion/output'};
stageFields = {'image_prepare_ms','inference_ms','archive_write_ms','point_extract_ms','fusion_output_latency_ms'};
labels = strcat(erase(string(latencyByStage.pipeline), 'lingbot_persistent_'), "\n", string(latencyByStage.window));
X = categorical(labels);
X = reordercats(X, labels);
stageVals = zeros(height(latencyByStage), numel(stageFields));
for i = 1:numel(stageFields)
    stageVals(:,i) = latencyByStage.(stageFields{i});
end

fig = figure('Color','w','Position',[80 80 1250 560]);
tiledlayout(1,2,'TileSpacing','compact','Padding','loose');
nexttile;
b = bar(X, stageVals, 'grouped');
grid on; ylabel('Stage time (ms)');
title('Figure 4A. Stage Timings Shown Independently');
legend(stageNames, 'Location','northwest');

% Explicitly label fast-path archive_write = 0 ms.
archiveIdx = find(strcmp(stageFields, 'archive_write_ms'));
fastRows = contains(string(latencyByStage.pipeline), 'fast');
for r = find(fastRows)'
    xtips = b(archiveIdx).XEndPoints(r);
    text(xtips, 35, '0 ms', 'HorizontalAlignment','center', 'Rotation',90, 'FontSize',8, 'Color',[0.70 0.15 0.12]);
end

nexttile;
totalVals = [latencyByStage.backend_total_ms latencyByStage.session_total_ms latencyByStage.wrapper_backend_latency_ms];
bar(X, totalVals, 'grouped');
grid on; ylabel('Total timing (ms)');
title('Figure 4B. Totals Shown Separately');
legend({'backend\_total\_ms','session\_total\_ms','wrapper\_backend\_latency\_ms'}, 'Location','northwest', 'Interpreter','tex');
annotation(fig, 'textbox', [0.07 0.015 0.88 0.06], 'String', ...
    'Source: latency\_by\_stage.csv. Grouped bars avoid implying mutually exclusive stage sums. Fast path archive\_write\_ms = 0 ms. session\_model\_load\_ms is session-level only.', ...
    'EdgeColor','none', 'HorizontalAlignment','center', 'FontSize',8, 'Interpreter','tex');
saveReportFigure(fig, outDir, 'fig4_persistent_latency_matlab');

%% Figure 6: ORB confidence/status/latency from real frame-level records
records = orbSummary.video_replay.records;
frameId = arrayfun(@(r) r.frame_id, records);
confidence = arrayfun(@(r) r.confidence, records);
latencyMs = arrayfun(@(r) r.latency_ms, records);
statusStrings = string({records.status});
localized = double(statusStrings == "localized");

fig = figure('Color','w','Position',[100 100 980 780]);
tiledlayout(3,1,'TileSpacing','compact','Padding','loose');
nexttile;
plot(frameId, confidence, '-o', 'LineWidth',1.5, 'MarkerSize',3, 'Color',[0.25 0.60 0.25]);
grid on; ylabel('Confidence'); ylim([0.95 1.005]);
title('Figure 6. ORB Same-scene Replay: Confidence, Status, and Timing');
nexttile;
stairs(frameId, localized, 'LineWidth',1.5, 'Color',[0.18 0.49 0.20]); hold on;
scatter(frameId, localized, 16, [0.18 0.49 0.20], 'filled');
grid on; ylabel('Status code'); yticks([0 1]); yticklabels({'not localized','localized'});
nexttile;
plot(frameId, latencyMs, '-o', 'LineWidth',1.4, 'MarkerSize',3, 'Color',[0.25 0.45 0.75]);
grid on; xlabel('Video frame id'); ylabel('Latency (ms)');
annotation(fig, 'textbox', [0.08 0.005 0.86 0.05], 'String', ...
    'Source: orb\_localization\_summary.json video\_replay.records, 30 frame-level records. Accepted localization ratio/confidence, not physical positioning accuracy.', ...
    'EdgeColor','none', 'HorizontalAlignment','center', 'FontSize',8, 'Interpreter','tex');
saveReportFigure(fig, outDir, 'fig6_orb_replay_matlab');

%% Figure 7: One-page key results table as an image
fig = figure('Color','w','Position',[100 100 850 460]);
axis off;
title('Key Results For One-page Report', 'FontWeight','bold');
rows = {
    'Unit tests', unitTestsResult;
    'Prediction replay updates', predictionUpdatesResult;
    'Final voxel count', finalVoxelResult;
    'Prediction replay latency', predictionLatencyResult;
    'Persistent model load', persistentModelLoadResult;
    'Fast path window 2 latency', fastPathWindow2Result;
    'ORB same-scene replay', orbReplayResult;
    'RTSP live benchmark', rtspResult
};
x0 = 0.08; y0 = 0.82; rowH = 0.085;
text(x0, y0+0.07, 'Item', 'FontWeight','bold');
text(0.50, y0+0.07, 'Result', 'FontWeight','bold');
for i = 1:size(rows,1)
    y = y0 - (i-1)*rowH;
    rectangle('Position',[0.06 y-0.035 0.84 rowH], 'FaceColor', [0.97 0.98 1.00], 'EdgeColor',[0.80 0.84 0.88]);
    text(x0, y, rows{i,1}, 'VerticalAlignment','middle');
    text(0.50, y, rows{i,2}, 'VerticalAlignment','middle');
end
text(0.06, 0.06, 'Guardrail: ORB accepted localization ratio is not physical localization accuracy; position/yaw error is NOT AVAILABLE without ground truth.', ...
    'FontSize',9, 'Color',[0.5 0.1 0.1]);
saveReportFigure(fig, outDir, 'fig7_key_results_table_matlab');

fprintf('Done. Figures exported to: %s\n', outDir);

%% Local helper functions
function rect = drawBox(ax, pos, label, faceColor, edgeColor, boxStyle)
    rectangle(ax, 'Position', pos, 'FaceColor', faceColor, 'EdgeColor', edgeColor, boxStyle{:});
    text(ax, pos(1)+pos(3)/2, pos(2)+pos(4)/2, label, ...
        'HorizontalAlignment','center', 'VerticalAlignment','middle', 'FontSize',9);
    rect = pos;
end

function drawArrow(ax, a, b, mode)
    switch mode
        case 'right-left'
            p1 = [a(1)+a(3), a(2)+a(4)/2];
            p2 = [b(1), b(2)+b(4)/2];
        case 'bottom-top'
            p1 = [a(1)+a(3)/2, a(2)];
            p2 = [b(1)+b(3)/2, b(2)+b(4)];
        otherwise
            error('unknown arrow mode');
    end
    quiver(ax, p1(1), p1(2), p2(1)-p1(1), p2(2)-p1(2), 0, ...
        'Color',[0.20 0.20 0.20], 'LineWidth',1.2, 'MaxHeadSize',0.35);
end

function out = formatInteger(value)
    raw = sprintf('%.0f', value);
    reversed = fliplr(raw);
    groups = regexp(reversed, '.{1,3}', 'match');
    out = fliplr(strjoin(groups, ','));
end

function saveReportFigure(fig, outDir, name)
    pngPath = fullfile(outDir, [name '.png']);
    svgPath = fullfile(outDir, [name '.svg']);
    try
        exportgraphics(fig, pngPath, 'Resolution', 220);
        exportgraphics(fig, svgPath, 'ContentType', 'vector');
    catch
        print(fig, pngPath, '-dpng', '-r220');
        print(fig, svgPath, '-dsvg');
    end
end
