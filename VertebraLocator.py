import logging
import os
import csv

import json
import vtk

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from DICOMLib import DICOMUtils

# from __main__ import qt

from xnat import SimpleXNAT


#
# VertebraLocator
#

class VertebraLocator(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Vertebra Locator"
        self.parent.categories = ["Annotations"]
        self.parent.dependencies = ["Markups", "DICOM"]
        self.parent.contributors = ["David Drobny (KCL), Marc Modat (KCL)"]
        self.parent.helpText = """
        This module is used to facilitate vertebra localisation and annotation on images imported 
        from an XNAT server
        See more information in <a href="https://github.com/KCL-BMEIS/SpineAnnotationSlicelet</a>.
        """
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = """
        This file was originally developed by David Drobny, KCL, and Marc Modat, KCL and was 
        partially funded by <grant>.
        """
        # Additional initialization step after application startup is complete
        # slicer.app.connect("startupCompleted()", registerSampleData)


#
# Register sample data sets in Sample Data module
#

def registerSampleData():
    """
    Add data sets to Sample Data module.
    """
    # It is always recommended to provide sample data for users to make it easy to try the module,
    # but if no sample data is available then this method (and associated startupCompleted signal
    # connection) can be removed.

    import SampleData
    iconsPath = os.path.join(os.path.dirname(__file__), 'Resources/Icons')

    # To ensure that the source code repository remains small (can be downloaded and installed
    # quickly) it is recommended to store data sets that are larger than a few MB in a Github
    # release.

    # VertebraLocator1
    SampleData.SampleDataLogic.registerCustomSampleDataSource(
        # Category and sample name displayed in Sample Data module
        category='VertebraLocator',
        sampleName='VertebraLocator1',
        # Thumbnail should have size of approximately 260x280 pixels and stored in Resources/Icons folder.
        # It can be created by Screen Capture module, "Capture all views" option enabled, "Number of images" set to "Single".
        thumbnailFileName=os.path.join(iconsPath, 'VertebraLocator1.png'),
        # Download URL and target file name
        uris="https://github.com/Slicer/SlicerTestingData/releases/download/SHA256/998cb522173839c78657f4bc0ea907cea09fd04e44601f17c82ea27927937b95",
        fileNames='VertebraLocator1.nrrd',
        # Checksum to ensure file integrity. Can be computed by this command:
        #  import hashlib; print(hashlib.sha256(open(filename, "rb").read()).hexdigest())
        checksums='SHA256:998cb522173839c78657f4bc0ea907cea09fd04e44601f17c82ea27927937b95',
        # This node name will be used when the data set is loaded
        nodeNames='VertebraLocator1'
    )

    # VertebraLocator2
    SampleData.SampleDataLogic.registerCustomSampleDataSource(
        # Category and sample name displayed in Sample Data module
        category='VertebraLocator',
        sampleName='VertebraLocator2',
        thumbnailFileName=os.path.join(iconsPath, 'VertebraLocator2.png'),
        # Download URL and target file name
        uris="https://github.com/Slicer/SlicerTestingData/releases/download/SHA256/1a64f3f422eb3d1c9b093d1a18da354b13bcf307907c66317e2463ee530b7a97",
        fileNames='VertebraLocator2.nrrd',
        checksums='SHA256:1a64f3f422eb3d1c9b093d1a18da354b13bcf307907c66317e2463ee530b7a97',
        # This node name will be used when the data set is loaded
        nodeNames='VertebraLocator2'
    )


#
# VertebraLocatorWidget
#

class VertebraLocatorWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False
        self._xnat = None
        self._currentImage = None
        self._currentID = None
        self._folder = None

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/VertebraLocator.ui'))
        self.layout.addWidget(uiWidget)

        # Info on available MarkupWidgets:
        # qMRMLMarkupsDisplayNodeWidget = Display box
        # qMRMLMarkupsInteractionHandleWidget = Display - Interaction Handle
        # qMRMLMarkupsToolBar = markup node selector dropdown
        # qSlicerMarkupsPlaceWidget = buttons for placement mode, delete etc.
        # qSlicerSimpleMarkupsWidget = label list and control buttons

        # widget = slicer.qSlicerSimpleMarkupsWidget()
        # self.layout.addWidget(widget)

        # w = slicer.qSlicerMarkupsPlaceWidget()
        # w.setMRMLScene(slicer.mrmlScene)
        # markupsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode")
        # w.setCurrentNode(slicer.mrmlScene.GetNodeByID(markupsNode.GetID()))
        # Hide all buttons and only show place button
        # w.buttonsVisible = False
        # w.placeButton().show()
        # self.layout.addWidget(w)

        # # include markups module as widget - how to access/modify this??
        # # Different object than normal markups module
        # markupsModule = slicer.modules.markups.createNewWidgetRepresentation()
        # # # markupsModule.setMRMLScene(slicer.app.mrmlScene())
        # # # markupsModule.show()
        # markupsModule.createMarkupsGroupBox.hide()
        # markupsModule.createMarkupsGroupBox.hide()
        # markupsModule.displayCollapsibleButton.hide()
        # markupsModule.exportImportCollapsibleButton.hide()
        # markupsModule.measurementsCollapsibleButton.hide()
        #
        # # hide more elements of the controlpoint sub-widget
        # c = markupsModule.controlPointsCollapsibleButton
        # c.enabled = True
        # c.collapsed = False
        # c.label_3.hide()
        # c.listLockedUnlockedPushButton.hide()
        # c.fixedNumberOfControlPointsPushButton.hide()
        # c.visibilityAllControlPointsInListMenuButton.hide()
        # c.selectedAllControlPointsInListMenuButton.hide()
        # c.lockAllControlPointsInListMenuButton.hide()
        # c.missingControlPointPushButton.hide()
        # c.unsetControlPointPushButton.hide()
        # c.deleteAllControlPointsInListPushButton.hide()
        # c.CutControlPointsToolButton.hide()
        # c.CopyControlPointsToolButton.hide()
        # c.PasteControlPointsToolButton.hide()
        # c.label_coords.hide()
        # c.coordinatesComboBox.hide()
        # c.advancedCollapsibleButton.hide()
        #
        # c.activeMarkupTableWidget.connect("cellChanged(int, int)",
        #                                   markupsModule,
        #                                   "onActiveMarkupTableCellChanged(int, int)")
        #
        # c.activeMarkupTableWidget.connect("itemClicked(QTableWidgetItem*)",
        #                                   markupsModule,
        #                                   "onActiveMarkupTableCellClicked(QTableWidgetItem*)")
        #
        # c.activeMarkupTableWidget.connect("currentCellChanged(int, int, int, int)",
        #                                   markupsModule,
        #                                   "onActiveMarkupTableCurrentCellChanged(int, int, int, int)")
        #
        # c.activeMarkupTableWidget.connect("customContextMenuRequested(QPoint)",
        #                                   markupsModule,
        #                                   "onRightClickActiveMarkupTableWidget(QPoint)")
        # # c.activeMarkupTableWidget.setCurrentNode(
        # #     slicer.util.getModuleGui("markups")
        # #     self._parameterNode.GetNodeReference("InputVolume"))
        #
        # self.layout.addWidget(markupsModule)

        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = VertebraLocatorLogic()

        markupsLogic = slicer.modules.markups.logic()
        # activate persistent place mode for control points
        interactionNode = slicer.util.getNodesByClass("vtkMRMLInteractionNode")
        markupsLogic.StartPlaceMode(interactionNode)

        # hide various UI elements of Markups module
        m = slicer.util.getModuleGui("Markups")
        # run in slicer prompt to see all available children:
        # getModuleGui("Markups").children()
        m.findChild("QGroupBox", "createMarkupsGroupBox").hide()
        m.findChild("qMRMLCollapsibleButton", "displayCollapsibleButton").hide()
        m.findChild("qMRMLCollapsibleButton", "exportImportCollapsibleButton").hide()
        m.findChild("ctkCollapsibleButton", "measurementsCollapsibleButton").hide()

        # hide more elements of the controlpoint sub-widget
        c = m.findChild("ctkCollapsibleButton", "controlPointsCollapsibleButton")
        c.checked = True
        c.findChild("QLabel", "label_3").hide()
        c.findChild("QPushButton", "listLockedUnlockedPushButton").hide()
        c.findChild("QPushButton", "fixedNumberOfControlPointsPushButton").hide()
        c.findChild("ctkMenuButton", "visibilityAllControlPointsInListMenuButton").hide()
        c.findChild("ctkMenuButton", "selectedAllControlPointsInListMenuButton").hide()
        c.findChild("ctkMenuButton", "lockAllControlPointsInListMenuButton").hide()
        c.findChild("QPushButton", "missingControlPointPushButton").hide()
        c.findChild("QPushButton", "unsetControlPointPushButton").hide()
        c.findChild("QPushButton", "deleteAllControlPointsInListPushButton").hide()
        c.findChild("QToolButton", "CutControlPointsToolButton").hide()
        c.findChild("QToolButton", "CopyControlPointsToolButton").hide()
        c.findChild("QToolButton", "PasteControlPointsToolButton").hide()
        c.findChild("QLabel", "label_coords").hide()
        c.findChild("QComboBox", "coordinatesComboBox").hide()
        c.findChild("ctkCollapsibleGroupBox", "advancedCollapsibleButton").hide()

        # try and maximise control point table height
        c.findChild("QTableWidget", "activeMarkupTableWidget").setFixedHeight(470)
        # c.findChild("QTableWidget", "activeMarkupTableWidget").setSizePolicy(
        #     qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)

        # ########### #
        # Connections #
        # ########### #

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # These connections ensure that whenever user changes some settings on
        # the GUI, that is saved in the MRML scene (in the selected parameter node).
        self.ui.xnatBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
        self.ui.serverLineEdit.connect("textChanged(QString)",
                                       self.updateParameterNodeFromGUI)
        self.ui.userLineEdit.connect("textChanged(QString)",
                                     self.updateParameterNodeFromGUI)
        self.ui.passwordLineEdit.connect("textChanged(QString)",
                                         self.updateParameterNodeFromGUI)
        self.ui.filterLineEdit.connect("textChanged(QString)",
                                       self.updateParameterNodeFromGUI)
        self.ui.xmlLineEdit.connect("textChanged(QString)",
                                    self.updateParameterNodeFromGUI)
        self.ui.skipCheckBox.connect("toggled(bool)",
                                     self.updateParameterNodeFromGUI)

        # Buttons
        self.ui.buttonLoad.connect('clicked(bool)', self.onLoadButton)
        self.ui.buttonInitialize.connect('clicked(bool)', self.onInitializeButton)
        self.ui.buttonConfirm.connect('clicked(bool)', self.onConfirmButton)
        self.ui.buttonCancel.connect('clicked(bool)', self.onCancelButton)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

        # hide default Slicer UI elements
        slicer.util.setModuleHelpSectionVisible(False)
        slicer.util.setDataProbeVisible(False)
        slicer.util.setApplicationLogoVisible(False)

    def cleanup(self):
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()

    def enter(self):
        """
        Called each time the user opens this module.
        """
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self):
        """
        Called each time the user opens a different module.
        """
        # Do not react to parameter node changes (GUI will be updated when the
        # user enters into the module)
        self.removeObserver(self._parameterNode,
                            vtk.vtkCommand.ModifiedEvent,
                            self.updateGUIFromParameterNode)

    def onSceneStartClose(self, caller, event):
        """
        Called just before the scene is closed.
        """
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event):
        """
        Called just after the scene is closed.
        """
        # If this module is shown while the scene is closed then recreate a new
        # parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self):
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

    def setParameterNode(self, inputParameterNode):
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then
        the GUI must be updated immediately.
        """
        if inputParameterNode:
            self.logic.setDefaultParameters(inputParameterNode)

        # Unobserve previously selected parameter node and add an observer to
        # the newly selected. Changes of parameter node are observed so that
        # whenever parameters are changed by a script or any other module those
        # are reflected immediately in the GUI.
        if self._parameterNode is not None:
            self.removeObserver(self._parameterNode,
                                vtk.vtkCommand.ModifiedEvent,
                                self.updateGUIFromParameterNode)
        self._parameterNode = inputParameterNode

        # Initial GUI update
        self.updateGUIFromParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        """
        This method is called whenever parameter node is changed.
        The module GUI is updated to show the current state of the parameter node.
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Make sure GUI changes do not call updateParameterNodeFromGUI
        # (it could cause infinite loop)
        self._updatingGUIFromParameterNode = True

        self.ui.serverLineEdit.text = self._parameterNode.GetParameter("serverLineEdit")
        self.ui.userLineEdit.text = self._parameterNode.GetParameter("userLineEdit")
        self.ui.passwordLineEdit.text = self._parameterNode.GetParameter("passwordLineEdit")
        self.ui.xmlLineEdit.text = self._parameterNode.GetParameter("xmlLineEdit")
        self.ui.filterLineEdit.text = self._parameterNode.GetParameter("filterLineEdit")

        self.ui.xnatBox.checked = self._parameterNode.GetParameter("xnatBoxCollapsed") == "true"
        self.ui.skipCheckBox.checked = self._parameterNode.GetParameter("skipCheckBox") == "true"

        # All the GUI updates are done
        self._updatingGUIFromParameterNode = False

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """
        This method is called when the user makes any change in the GUI.
        The changes are saved into the parameter node (so that they are
        restored when the scene is saved and loaded).
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Modify all properties in a single batch
        wasModified = self._parameterNode.StartModify()

        self._parameterNode.SetParameter("serverLineEdit", self.ui.serverLineEdit.text)
        self._parameterNode.SetParameter("userLineEdit", self.ui.userLineEdit.text)
        self._parameterNode.SetParameter("passwordLineEdit", self.ui.passwordLineEdit.text)
        self._parameterNode.SetParameter("xmlLineEdit", self.ui.xmlLineEdit.text)
        self._parameterNode.SetParameter("filterLineEdit", self.ui.filterLineEdit.text)
        self._parameterNode.SetParameter("skipCheckBox",
                                         "true" if self.ui.skipCheckBox.checked else "false")
        self._parameterNode.SetParameter("xnatBoxCollapsed",
                                         "true" if self.ui.xnatBox.checked else "false")

        self._parameterNode.EndModify(wasModified)

    def onInitializeButton(self):
        """
        Run initial set-up when user clicks "Initialise" button. Removes existing fiducial nodes if
        they exist, then create new ones for each spine segment. Naming format and color are set
        for each region. Vertebra control points are pre-generated and set to empty coordinates.
        """
        with slicer.util.tryWithErrorDisplay("Failed to initialise Markups.",
                                             waitCursor=True):

            defaultDescription = "none"
            markupsLogic = slicer.modules.markups.logic()

            for markup in ["C", "T", "L", "S"]:
                try:
                    slicer.mrmlScene.RemoveNode(slicer.util.getNode(markup))
                except slicer.util.MRMLNodeNotFoundException:
                    pass

            idC = markupsLogic.AddNewFiducialNode("C")
            slicer.util.getNode(idC).SetControlPointLabelFormat("%N%d")
            # slicer.util.getNode(idC).GetDisplayNode().SetActiveColor()
            slicer.util.getNode(idC).GetDisplayNode().SetSelectedColor(0.8, 0.8, 0.2)
            for i in range(7):
                slicer.util.getNode(idC).AddControlPoint(0, 0, 0)
                slicer.util.getNode(idC).UnsetNthControlPointPosition(i)
                slicer.util.getNode(idC).SetNthControlPointDescription(i, defaultDescription)
            slicer.util.getNode(idC).SetDescription("Cervical Spine")

            idT = markupsLogic.AddNewFiducialNode("T")
            slicer.util.getNode(idT).SetControlPointLabelFormat("%N%d")
            slicer.util.getNode(idT).GetDisplayNode().SetSelectedColor(1.0, 0.25, 0.5)
            for i in range(12):
                slicer.util.getNode(idT).AddControlPoint(0, 0, 0)
                slicer.util.getNode(idT).UnsetNthControlPointPosition(i)
                slicer.util.getNode(idT).SetNthControlPointDescription(i, defaultDescription)
            slicer.util.getNode(idT).SetDescription("Thoracic Spine")

            idL = markupsLogic.AddNewFiducialNode("L")
            slicer.util.getNode(idL).SetControlPointLabelFormat("%N%d")
            slicer.util.getNode(idL).GetDisplayNode().SetSelectedColor(0.25, 0.5, 1.0)
            for i in range(5):
                slicer.util.getNode(idL).AddControlPoint(0, 0, 0)
                slicer.util.getNode(idL).UnsetNthControlPointPosition(i)
                slicer.util.getNode(idL).SetNthControlPointDescription(i, defaultDescription)
            slicer.util.getNode(idL).SetDescription("Lumbar Spine")

            idS = markupsLogic.AddNewFiducialNode("S")
            slicer.util.getNode(idS).SetControlPointLabelFormat("%N%d")
            slicer.util.getNode(idS).GetDisplayNode().SetSelectedColor(0.25, 1.0, 0.5)
            for i in range(3):
                slicer.util.getNode(idS).AddControlPoint(0, 0, 0)
                slicer.util.getNode(idS).UnsetNthControlPointPosition(i)
                slicer.util.getNode(idS).SetNthControlPointDescription(i, defaultDescription)
            slicer.util.getNode(idS).SetDescription("Sacrum")

            # ToDo:
            # Node List: SetDescription seems bugged and resets
            # include this module/widget in Markups module
            # register shortcuts for extra functionality in markups?

            # # test to add this widget to markups@
            # self.createNewWidgetRepresentation()
            # m = slicer.util.getModuleGui("Markups")
            # m.layout().addWidget(VertebraLocatorWidget())

            return

    def onLoadButton(self):
        """
        Establish the connection to an XNAT server with the provided user credentials.
        """
        with slicer.util.tryWithErrorDisplay("Failed to connect to XNAT.",
                                             waitCursor=True):
            if self._xnat is None:
                # create xnat object
                self._xnat = SimpleXNAT(self.ui.serverLineEdit.text,
                                        user=self.ui.userLineEdit.text,
                                        pwd=self.ui.passwordLineEdit.text,
                                        xml_query_file=self.ui.xmlLineEdit.text)
                # initialize iterator
                iter(self._xnat)

                # instantiate the DICOM browser
                slicer.util.selectModule("DICOM")
                slicer.util.selectModule("VertebraLocator")
            # load first image
            self._next()
            self.onInitializeButton()

    def onConfirmButton(self):
        """
        Save and export markups to xnat, then load the next image if available
        when user clicks "Confirm | Next Image" button.
        """
        with slicer.util.tryWithErrorDisplay("Failed to save annotations to XNAT.",
                                             waitCursor=True):

            # # json file
            # path = os.path.join(self._folder, self._currentID+".json")
            # slicer.util.saveNode(slicer.util.getNode("C"), path)
            # self._xnat.upload_annotations(path)

            # alternatively, save markups as csv file
            markupsLogic = slicer.modules.markups.logic()

            combined_csv = []
            for markup in ["C", "T", "L", "S"]:
                path = os.path.join(self._folder, self._currentID+"_"+markup+".csv")
                markupsLogic.ExportControlPointsToCSV(slicer.util.getNode(markup), path)

                with open(path, newline='') as file:
                    reader = csv.reader(file)
                    for i, row in enumerate(reader):
                        print(i)
                        if not markup == "C" and i==0:
                            continue
                        print(row)
                        combined_csv.append(row)

            path = os.path.join(self._folder, self._currentID + ".csv")
            with open(path, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerows(combined_csv)

            print(combined_csv)
            self._next()
            self.onInitializeButton()

    def onCancelButton(self):
        """
        Don't save annotations to XNAT, continue to next image.
        """
        with slicer.util.tryWithErrorDisplay("Failed to continue.",
                                             waitCursor=True):
            # ToDo: desireable to save tag in XNAT, that image was processed
            #  with no annotation to save
            self._next()
            self.onInitializeButton()

    def _next(self):
        """
        Utility function to load and switch to the next image.
        """
        subject = next(self._xnat)
        self._currentID = subject['session_label'].values[0]
        self._folder = self._xnat.get_scan_dicom_folder()
        # print(dicomFolder)

        # delete current image to not litter the viewer
        if self._currentImage is not None:
            slicer.mrmlScene.RemoveNode(slicer.util.getNode(self._currentImage))

        with DICOMUtils.TemporaryDICOMDatabase() as db:
            DICOMUtils.importDicom(self._folder, db)
            # create loadable volumes from dicom
            slicer.modules.DICOMWidget.browserWidget.examineForLoading()
            # load volume
            patient_name = self._currentID.split("_", 1)[0]
            loadedNodeIDs = DICOMUtils.loadPatientByName(patient_name)
            # store reference so volume can be deleted
            self._currentImage = loadedNodeIDs[0]
            # update viewers to new volume
            slicer.util.setSliceViewerLayers(background=self._currentImage)

#
# VertebraLocatorLogic
#

class VertebraLocatorLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual computation done by your
    module.  The interface should be such that other python code can import
    this class and make use of the functionality without requiring an instance
    of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self):
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)

    def setDefaultParameters(self, parameterNode):
        """
        Initialize parameter node with default settings.
        """
        if not parameterNode.GetParameter("Threshold"):
            parameterNode.SetParameter("Threshold", "100.0")
        if not parameterNode.GetParameter("Invert"):
            parameterNode.SetParameter("Invert", "false")

    def process(self, inputVolume, outputVolume, imageThreshold, invert=False, showResult=True):
        """
        Run the processing algorithm.
        Can be used without GUI widget.
        :param inputVolume: volume to be thresholded
        :param outputVolume: thresholding result
        :param imageThreshold: values above/below this threshold will be set to 0
        :param invert: if True then values above the threshold will be set to 0, otherwise values below are set to 0
        :param showResult: show output volume in slice viewers
        """

        if not inputVolume or not outputVolume:
            raise ValueError("Input or output volume is invalid")

        import time
        startTime = time.time()
        logging.info('Processing started')

        # Compute the thresholded output volume using the "Threshold Scalar Volume" CLI module
        cliParams = {
            'InputVolume': inputVolume.GetID(),
            'OutputVolume': outputVolume.GetID(),
            'ThresholdValue': imageThreshold,
            'ThresholdType': 'Above' if invert else 'Below'
        }
        cliNode = slicer.cli.run(slicer.modules.thresholdscalarvolume, None, cliParams, wait_for_completion=True, update_display=showResult)
        # We don't need the CLI module node anymore, remove it to not clutter the scene with it
        slicer.mrmlScene.RemoveNode(cliNode)

        stopTime = time.time()
        logging.info(f'Processing completed in {stopTime-startTime:.2f} seconds')


#
# VertebraLocatorTest
#

class VertebraLocatorTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_VertebraLocator1()

    def test_VertebraLocator1(self):
        """ Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")

        # Get/create input data

        import SampleData
        registerSampleData()
        inputVolume = SampleData.downloadSample('VertebraLocator1')
        self.delayDisplay('Loaded test data set')

        inputScalarRange = inputVolume.GetImageData().GetScalarRange()
        self.assertEqual(inputScalarRange[0], 0)
        self.assertEqual(inputScalarRange[1], 695)

        outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        threshold = 100

        # Test the module logic

        logic = VertebraLocatorLogic()

        # Test algorithm with non-inverted threshold
        logic.process(inputVolume, outputVolume, threshold, True)
        outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], threshold)

        # Test algorithm with inverted threshold
        logic.process(inputVolume, outputVolume, threshold, False)
        outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], inputScalarRange[1])

        self.delayDisplay('Test passed')
