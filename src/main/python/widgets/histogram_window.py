from functools import partial

import numpy as np
import pandas as pd
from PyQt5.QtWidgets import QFileDialog

import lib.math
import lib.plotting
import lib.utils
from global_variables import GlobalVariables as gvars
from ui._HistogramWindow import Ui_HistogramWindow
from ui._MenuBar import Ui_MenuBar
from widgets.base_window import BaseWindow


class HistogramWindow(BaseWindow):
    def __init__(self):
        super().__init__()
        # Histogram data
        self.E = None
        self.E_un = None
        self.S = None
        self.S_un = None
        self.DD, self.DA, self.corrs, = None, None, None

        self.alpha = None
        self.delta = None
        self.beta = None
        self.gamma = None

        self.gauss_params = None
        self.best_k = None
        self.n_samples = None
        self.n_points = None
        self.len = None

        # Plotting parameters
        self.marg_bins = np.arange(-0.1, 1.1, 0.02)
        self.xpts = np.linspace(-0.1, 1.1, 300)

        self.ui = Ui_HistogramWindow()
        self.ui.setupUi(self)

        self.da_label = r"$\mathbf{DA}$"
        self.dd_label = r"$\mathbf{DD}$"

        self.setupFigureCanvas(ax_type="histwin")

        self.setupPlot()
        self.connectUi()

    def enablePerWindow(self):
        """
        Disables specific commands that should be unavailable for certain
        window types. Export commands should be accessible from all windows
        (no implicit behavior).
        """
        self.ui: Ui_MenuBar

        menulist = (self.ui.actionFormat_Plot,)
        for menu in menulist:
            menu.setEnabled(True)

    def showDensityWindowInspector(self):
        """
        Opens the inspector (modal) window to format the current plot
        """
        if self.isActiveWindow():
            self.inspectors[gvars.DensityWindowInspector].show()

    def exportHistogramData(self):
        """
        Exports histogram data for selected traces
        """
        exp_txt, date_txt = self.returnInfoHeader()

        directory = (
            self.getConfig(gvars.key_lastOpenedDir) + "/E_S_Histogram.txt"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, directory=directory
        )  # type: str, str

        self.getHistogramData()

        if path != "":
            if not path.split("/")[-1].endswith(".txt"):
                path += ".txt"

            # Exports all the currently plotted datapoints
            if self.ui.applyCorrectionsCheckBox.isChecked():
                E, S = self.E, self.S
            else:
                E, S = self.E_un, self.S_un

            if E is not None:
                if np.all(np.isnan(S)):  # Exports Non-ALEX data
                    df = pd.DataFrame({"E": E}).round(4)
                else:
                    df = pd.DataFrame({"E": E, "S": S}).round(
                        4
                    )  # Exports ALEX data
            else:
                df = pd.DataFrame({"E": [], "S": []})

            ntraces_txt = "N_traces: {}".format(self.n_samples)

            with open(path, "w") as f:
                f.write(
                    "{0}\n"
                    "{1}\n"
                    "{2}\n\n"
                    "{3}".format(
                        exp_txt,
                        date_txt,
                        ntraces_txt,
                        df.to_csv(index=False, sep="\t", na_rep="NaN"),
                    )
                )

    def unCheckAll(self):
        """
        Unchecks all list elements. Attribute check because they override
        "select", which is normally reserved for text fields
        """
        super().unCheckAll()
        if self.isVisible():
            self.refreshPlot()

    def checkAll(self):
        """
        Checks all list elements.
        """
        super().checkAll()
        if self.isVisible():
            self.refreshPlot()

    def connectUi(self):
        for f in (
            partial(self.fitGaussians, "auto"),
            partial(self.refreshPlot, True),
        ):
            self.ui.gaussianAutoButton.clicked.connect(f)

        for f in (self.fitGaussians,):
            self.ui.gaussianSpinBox.valueChanged.connect(f)

        for f in (self.fitGaussians,):
            self.ui.applyCorrectionsCheckBox.clicked.connect(f)

        for f in (self.fitGaussians,):
            self.ui.framesSpinBox.valueChanged.connect(f)

    def savePlot(self):
        """
        Saves plot with colors suitable for export (e.g. white background)
        for HistogramWindow.
        """
        self.setSavefigrcParams()
        self.canvas.defaultImageName = "2D histogram"
        self.canvas.toolbar.save_figure()
        self.refreshPlot()

    def setupPlot(self):
        """
        Set up plot for HistogramWindow.
        """
        self.canvas.fig.set_facecolor(gvars.color_gui_bg)

        for ax in self.canvas.axes:
            for spine in ax.spines.values():
                spine.set_edgecolor(gvars.color_gui_text)
                spine.set_linewidth(0.5)
            ax.tick_params(axis="both", colors=gvars.color_gui_text, width=0.5)

    def getHistogramData(self, n_first_frames="all"):
        """
        Returns pooled E and S_app data before bleaching, for each trace.
        The loops take approx. 0.1 ms per trace, and it's too much trouble
        to lower it further.
        Also return DD, DA, and Pearson correlation data.
        """
        if n_first_frames == "all":
            n_first_frames = None
        elif n_first_frames == "spinbox":
            n_first_frames = self.ui.framesSpinBox.value()
        else:
            raise ValueError("n_first_frames must be either 'all' or 'spinbox'")

        self.none_ = (
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        (
            self.E,
            self.S,
            self.DD,
            self.DA,
            self.corrs,
            self.E_un,
            self.S_un,
        ) = self.none_

        checkedTraces = [
            trace for trace in self.data.traces.values() if trace.is_checked
        ]

        self.len = len(checkedTraces)
        self.n_samples = self.len
        self.n_points = 0
        alpha = self.getConfig(gvars.key_alphaFactor)
        delta = self.getConfig(gvars.key_deltaFactor)

        DA, DD, E_app, S_app, lengths, corrs = [], [], [], [], [], []
        for trace in checkedTraces:
            E, S = lib.math.drop_bleached_frames(
                intensities=trace.get_intensities(),
                bleaches=trace.get_bleaches(),
                alpha=alpha,
                delta=delta,
                max_frames=n_first_frames,
                blink_intervals=trace.blink_intervals,
            )
            E_app.extend(E)
            S_app.extend(S)
            _, I_DD, I_DA, I_AA = lib.math.correct_DA(trace.get_intensities())
            trace.calculate_stoi()

            end_frame = trace.first_bleach
            if end_frame is None:
                end_frame = len(I_DD)

            I_DD = lib.math.exclude_blink_intervals(
                I_DD[: end_frame], trace.blink_intervals
            )
            I_DA = lib.math.exclude_blink_intervals(
                I_DA[: end_frame], trace.blink_intervals
            )

            DD.append(I_DD)
            DA.append(I_DA)
            _len = len(E)
            lengths.append(_len)
            self.n_points += _len

        self.DD = np.concatenate(DD).flatten() if len(DD) > 0 else np.array([])
        self.DA = np.concatenate(DA).flatten() if len(DA) > 0 else np.array([])

        self.E_un, self.S_un = lib.math.trim_ES(E_app, S_app)
        self.n_points = len(self.E_un)
        self.data.histData.n_samples = self.n_samples
        self.data.histData.n_points = self.n_points

        # Skip ensemble correction if stoichiometry is missing
        if not lib.math.contains_nan(self.S_un):
            if len(self.E_un) > 0:
                beta, gamma = lib.math.beta_gamma_factor(
                    E_app=self.E_un, S_app=self.S_un
                )
                E_real, S_real, = [], []
                for trace in checkedTraces:
                    E, S = lib.math.drop_bleached_frames(
                        intensities=trace.get_intensities(),
                        bleaches=trace.get_bleaches(),
                        alpha=alpha,
                        delta=delta,
                        beta=beta,
                        gamma=gamma,
                        max_frames=n_first_frames,
                        blink_intervals=trace.blink_intervals,
                    )
                    E_real.extend(E)
                    S_real.extend(S)
                self.E, self.S = lib.math.trim_ES(E_real, S_real)
                self.beta = beta
                self.gamma = gamma
        else:
            self.E = self.E_un

        self.alpha = alpha
        self.delta = delta

    def fitGaussians(self, states):
        """
        Fits multiple gaussians to the E data
        """
        corrected = self.ui.applyCorrectionsCheckBox.isChecked()
        E = self.E if corrected else self.E_un

        if E is not None and len(E) >= 2:
            n_components = (
                (1, 6) if states == "auto" else self.ui.gaussianSpinBox.value()
            )

            best_model, params = lib.math.fit_gaussian_mixture(
                X=E,
                min_n_components=np.min(n_components),
                max_n_components=np.max(n_components),
            )

            self.gauss_params = params
            self.best_k = best_model.n_components

            self.ui.gaussianSpinBox.setValue(self.best_k)
            self.ui.gaussianSpinBox.repaint()
        else:
            self.gauss_params = None
            self.best_k = None

        self.refreshPlot()

    def plotDefaultElements(self):
        """
        Re-plot non-persistent plot settings (otherwise will be overwritten
        by ax.clear())
        """
        self.canvas.ax_ctr.set_xlim(-0.1, 1.1)
        self.canvas.ax_ctr.set_ylim(-0.1, 1.1)

        for ax in self.canvas.axes_marg:
            for tk in ax.get_xticklabels():
                tk.set_visible(False)
            for tk in ax.get_yticklabels():
                tk.set_visible(False)

        self.canvas.ax_top.set_xlabel(r"$\mathbf{E}_{FRET}$")
        self.canvas.ax_top.xaxis.set_label_position("top")

        self.canvas.ax_rgt.set_ylabel(r"$\mathbf{S}$")
        self.canvas.ax_rgt.yaxis.set_label_position("right")

    def plotTop(self, corrected, color=None):
        """
        Plots the top left top marginal histogram (E).
        """
        E = self.E if corrected else self.E_un

        if E is not None:
            self.canvas.ax_top.clear()
            self.canvas.ax_top.hist(
                E,
                bins=self.marg_bins,
                color=color or gvars.color_orange,
                alpha=0.8,
                density=True,
                histtype="stepfilled",
            )

        if self.gauss_params is not None:
            joint_dist = []
            xpts = self.xpts
            for (m, s, w) in self.gauss_params:
                _, y = lib.plotting.plot_gaussian(
                    mean=m, sigma=s, weight=w, x=xpts, ax=self.canvas.ax_top
                )
                joint_dist.append(y)

            # Sum of all gaussians (joint distribution)
            joint_dist = np.sum(joint_dist, axis=0)

            self.canvas.ax_top.plot(
                xpts,
                joint_dist,
                color=gvars.color_grey,
                alpha=1,
                zorder=10,
                ls="--",
            )

            self.canvas.ax_top.set_xlim(-0.1, 1.1)

    def plotRight(self, corrected, color=None):
        """
        Plots the top left right marginal histogram (S).
        """
        S = self.S if corrected else self.S_un
        self.canvas.ax_rgt.set_ylabel("Stoichiometry")
        self.canvas.ax_rgt.yaxis.set_label_position("right")
        if S is not None:
            self.canvas.ax_rgt.clear()
            self.canvas.ax_rgt.hist(
                S,
                bins=self.marg_bins,
                color=color or gvars.color_purple,
                alpha=0.8,
                density=True,
                histtype="stepfilled",
                orientation="horizontal",
            )

        # The stoichiometry histogram is oriented horizontally, meaning the
        # y-axis holds the S values. The limits should therefore be applied to
        # the y-axis instead of the x-axis to avoid clipping the histogram.
        self.canvas.ax_rgt.set_ylim(-0.1, 1.1)

    def plotCenter(self, corrected, params):
        """
        Plots the top left center E+S contour plot.
        """
        S = self.S if corrected else self.S_un
        E = self.E if corrected else self.E_un

        (
            bandwidth,
            resolution,
            n_colors,
            overlay_pts,
            pts_alpha,
            show_density,
            _e_color,
            _s_color,
            cmap,
        ) = params
        self.inspectors[gvars.DensityWindowInspector].setInspectorConfigs(params)

        self.canvas.ax_ctr.clear()

        n_equals_txt = "$N_{{traces}}$ = {}\n$N_{{data}}$ = {}".format(
            self.n_samples,
            self.n_points,
        )

        self.canvas.ax_ctr.text(
            x=0,
            y=0.9,
            s=n_equals_txt,
            color=gvars.color_gui_text,
        )

        if self.gauss_params is not None:
            for n, gauss_params in enumerate(self.gauss_params):
                m, s, w = gauss_params
                self.canvas.ax_ctr.text(
                    x=0.6,
                    y=0.15 - 0.05 * n,
                    s=r"$\mu_{}$ = {:.2f} $\pm$ {:.2f} ({:.2f})".format(
                        n + 1, m, s, w
                    ),
                    color=gvars.color_gui_text,
                    zorder=10,
                )

        for n, (factor, name) in enumerate(
            zip(
                (self.alpha, self.delta, self.beta, self.gamma),
                ("alpha", "delta", "beta", "gamma"),
            )
        ):
            self.canvas.ax_ctr.text(
                x=0.0,
                y=0.15 - 0.05 * n,
                s=r"$\{}$ = {:.2f}".format(name, factor),
                color=gvars.color_gui_text,
                zorder=10,
            )

        if S is not None:
            if show_density:
                c = lib.math.contour_2d(
                    xdata=E,
                    ydata=S,
                    bandwidth=bandwidth / 200,
                    resolution=resolution,
                    kernel="linear",
                    n_colors=n_colors,
                )
                self.canvas.ax_ctr.contourf(*c, cmap=cmap)

            if overlay_pts:
                # Conversion factor, because sliders can't do [0,1]
                self.canvas.ax_ctr.scatter(
                    E, S, s=20, color="black", zorder=1, alpha=pts_alpha / 20
                )
            self.canvas.ax_ctr.axhline(
                0.5, color="black", alpha=0.3, lw=0.5, ls="--", zorder=2
            )

    def plotAll(self, corrected):
        params = self.inspectors[gvars.DensityWindowInspector].returnInspectorValues()
        (
            bandwidth,
            resolution,
            n_colors,
            overlay_pts,
            pts_alpha,
            show_density,
            e_color,
            s_color,
            cmap,
        ) = params
        self.plotTop(corrected, color=gvars.plot_color_options.get(e_color, e_color))
        if self.S is not None:
            self.plotCenter(corrected, params)
            self.plotRight(corrected, color=gvars.plot_color_options.get(s_color, s_color))

        self.canvas.draw()

    def refreshPlot(self, autofit=False):
        """
        Refreshes plot with currently selected traces. Plot to refresh can be
        top, right (histograms) or center (scatterplot), or all.
        """
        corrected = self.ui.applyCorrectionsCheckBox.isChecked()
        try:
            self.getHistogramData()
            for ax in self.canvas.axes:
                ax.clear()
            if self.E is not None:
                # Force unchecked
                if self.S is None:
                    self.ui.applyCorrectionsCheckBox.setChecked(False)
                    corrected = False
                self.plotDefaultElements()
                self.plotAll(corrected)
            else:
                self.plotDefaultElements()
        except (AttributeError, ValueError):
            pass

        self.plotDefaultElements()
        self.canvas.draw()

    def _debug(self):
        pass
