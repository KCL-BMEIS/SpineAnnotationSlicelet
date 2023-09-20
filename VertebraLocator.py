import logging
import os
import csv
import json
import vtk

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from DICOMLib import DICOMUtils
from copy import deepcopy
from tempfile import TemporaryDirectory

from __main__ import qt

from ImageIterator import SimpleXNAT, LocalFileIterator


#
# VertebraLocator module
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

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/VertebraLocator2.ui'))
        self.layout.addWidget(uiWidget)
        uiWidget2 = VertebraLocatorSecondaryWidget()
        self.layout.addWidget(uiWidget2)

        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = VertebraLocatorLogic()

        # ########### #
        # Connections #
        # ########### #

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent,
                         self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Buttons
        self.ui.pushButton.connect('clicked(bool)', self.onButton)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

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

        self._parameterNode.EndModify(wasModified)

    def onButton(self):
        """
        Create a new widget in the GUI of the Markups module to combine the
        needed functionality into one module. Hide UI elements not needed for
        the intended workflow.
        """
        with slicer.util.tryWithErrorDisplay("Failed to add widget to Markups",
                                             waitCursor=True):
            slicer.util.selectModule("Markups")

            markups = slicer.util.getModuleGui("Markups")
            newWidget = VertebraLocatorSecondaryWidget()
            # initialise paramter of new widget with those of widget from the
            # VertebraLocator module
            newWidget.name = "VertebraLocatorSecondaryWidget"
            newWidget.setParameterNode(self._parameterNode)
            # check whether Markups module already has a widget attached
            if markups.findChild("QWidget", "VertebraLocatorSecondaryWidget"):
                print("Widget already attached to Markups module")
            else:
                markups.layout().addWidget(newWidget)

            # prune Markups GUI down to needed functionality

            # hide various UI elements of Markups module
            m = slicer.util.getModuleGui("Markups")
            # run in slicer prompt to see all available children:
            # slicer.util.getModuleGui("Markups").children()
            m.findChild("QGroupBox", "createMarkupsGroupBox").hide()
            m.findChild("qMRMLCollapsibleButton", "displayCollapsibleButton").hide()
            m.findChild("qMRMLCollapsibleButton", "exportImportCollapsibleButton").hide()
            m.findChild("ctkCollapsibleButton", "measurementsCollapsibleButton").hide()
            # m.findChild("ctkExpandableWidget", "ResizableFrame").hide()   # Node list
            m.findChild("ctkExpandableWidget", "ResizableFrame").setFixedHeight(150)

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
            c.findChild("QLabel", "label").hide()
            c.findChild("QComboBox", "jumpModeComboBox").hide()

            # if template has fixed controlpoints:
            c.findChild("QPushButton", "deleteControlPointPushButton").hide()

            # activate slice intersection for the slice viewer
            c.findChild("ctkCheckBox", "sliceIntersectionsVisibilityCheckBox").checked = True

            # try and maximise control point table height
            # c.findChild("QTableWidget", "activeMarkupTableWidget").setFixedHeight(670)
            m.findChild("ctkDynamicSpacer", "DynamicSpacer").hide()
            c.findChild("QTableWidget", "activeMarkupTableWidget").setSizePolicy(
                qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)

            # hide first columns of table
            c.findChild("QTableWidget", "activeMarkupTableWidget").setColumnHidden(0, True)
            c.findChild("QTableWidget", "activeMarkupTableWidget").setColumnHidden(1, True)
            c.findChild("QTableWidget", "activeMarkupTableWidget").setColumnHidden(2, True)


#
# VertebraLocatorSecondaryWidget
#

class VertebraLocatorSecondaryWidget(qt.QWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        # ScriptedLoadableModuleWidget.__init__(self, parent)
        qt.QWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False
        self._imageIterator = None
        self._currentImage = None
        self._currentAnnotation = None
        # self._currentID = None
        # self._folder = None
        self.setup()

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        # ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        cwd = os.path.dirname(os.path.abspath(__file__))
        uiWidget = slicer.util.loadUI(os.path.join(cwd, "Resources/UI/VertebraLocator.ui"))
        layout = qt.QVBoxLayout()
        layout.addWidget(uiWidget)
        self.setLayout(layout)

        # Info on available MarkupWidgets:
        # qMRMLMarkupsDisplayNodeWidget = Display box
        # qMRMLMarkupsInteractionHandleWidget = Display - Interaction Handle
        # qMRMLMarkupsToolBar = markup node selector dropdown
        # qSlicerMarkupsPlaceWidget = buttons for placement mode, delete etc.
        # qSlicerSimpleMarkupsWidget = label list and control buttons
        # controlPointsCollapsibleButton is not made available (yet)

        # widget = slicer.qSlicerSimpleMarkupsWidget()
        # self.layout.addWidget(widget)

        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = VertebraLocatorLogic()

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
        self.ui.filterFramesLineEdit.connect("textChanged(QString)",
                                             self.updateParameterNodeFromGUI)
        self.ui.filterSubjectLineEdit.connect("textChanged(QString)",
                                             self.updateParameterNodeFromGUI)
        self.ui.filterSeriesLineEdit.connect("textChanged(QString)",
                                             self.updateParameterNodeFromGUI)
        self.ui.xmlLineEdit.connect("textChanged(QString)",
                                    self.updateParameterNodeFromGUI)
        self.ui.localFolderLineEdit.connect("textChanged(QString)",
                                          self.updateParameterNodeFromGUI)
        self.ui.skipCheckBox.connect("toggled(bool)",
                                     self.updateParameterNodeFromGUI)

        # Buttons
        self.ui.buttonLoad.connect('clicked(bool)', self.onLoadButton)
        self.ui.buttonInitialize.connect('clicked(bool)', self.onInitializeButton)
        self.ui.buttonLoadAnnotation.connect('clicked(bool)', self.onLoadAnnotationButton)
        self.ui.buttonConfirm.connect('clicked(bool)', self.onConfirmButton)
        self.ui.buttonCancel.connect('clicked(bool)', self.onCancelButton)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

        # hide default Slicer UI elements
        slicer.util.setModuleHelpSectionVisible(False)
        # slicer.util.setDataProbeVisible(False)
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
        self.ui.filterSubjectLineEdit.text = self._parameterNode.GetParameter("filterSubjectLineEdit")
        self.ui.filterFramesLineEdit.text = self._parameterNode.GetParameter("filterFramesLineEdit")
        self.ui.filterSeriesLineEdit.text = self._parameterNode.GetParameter("filterSeriesLineEdit")
        self.ui.localFolderLineEdit.text = self._parameterNode.GetParameter("localFolderLineEdit")

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
        self._parameterNode.SetParameter("filterSubjectLineEdit", self.ui.filterSubjectLineEdit.text)
        self._parameterNode.SetParameter("filterFramesLineEdit", self.ui.filterFramesLineEdit.text)
        self._parameterNode.SetParameter("filterSeriesLineEdit", self.ui.filterSeriesLineEdit.text)
        self._parameterNode.SetParameter("localFolderLineEdit", self.ui.localFolderLineEdit.text)
        self._parameterNode.SetParameter("skipCheckBox",
                                         "true" if self.ui.skipCheckBox.checked else "false")
        self._parameterNode.SetParameter("xnatBoxCollapsed",
                                         "true" if self.ui.xnatBox.checked else "false")
        if self._imageIterator is not None:
            self._imageIterator.set_skip_annotated(self.ui.skipCheckBox.checked)

        self._parameterNode.EndModify(wasModified)

    def onInitializeButton(self):
        """
        Run initial set-up when user clicks "Initialise" button. Removes existing fiducial nodes if
        they exist, then create new ones for each spine segment. Naming format and color are set
        for each region. Vertebra control points are pre-generated and set to empty coordinates.
        """
        with slicer.util.tryWithErrorDisplay("Failed to initialise Markups.",
                                             waitCursor=True):

            markupsLogic = slicer.modules.markups.logic()

            # load template file
            template_path = os.path.join(os.path.dirname(__file__),
                                         "vertebra_landmark_template.mrk.json")
            nodeID = markupsLogic.LoadMarkups(template_path)

            slicer.util.getNode(nodeID).SetName("Vertebra L1")
            slicer.util.getNode(nodeID).SetDescription("please rename accordingly")

            # Move away from static definition to using template files
            #
            # defaultDescription = "none"     # default for description field of control points
            # # region labels and default numbers for the spinal regions
            # spineRegions = ["C", "T", "L", "S"]
            # spineRegionSizes = [7, 12, 5, 5]
            #
            # # remove previously created markup node, if exists
            # slicer.mrmlScene.RemoveNode(slicer.mrmlScene.GetFirstNodeByName("Vertebrae"))
            #
            # # create new markup node
            # nodeID = markupsLogic.AddNewFiducialNode("Vertebrae")
            # slicer.util.getNode(nodeID).SetControlPointLabelFormat("%N%d")
            # slicer.util.getNode(nodeID).GetDisplayNode().SetSelectedColor(0.8, 0.8, 0.2)
            # slicer.util.getNode(nodeID).SetDescription(
            #   "List for all vertebra annotations, one controlpoint per center of vertebral body")
            #
            # # create one control point per vertebra
            # i = 0   # counter for all set controlpoints/vertebrae
            # for region, n in zip(spineRegions, spineRegionSizes):
            #     for j in range(n):
            #         currentNode = slicer.mrmlScene.GetNodeByID(nodeID)
            #         currentNode.AddControlPoint(0, 0, 0)
            #         currentNode.UnsetNthControlPointPosition(i)
            #         currentNode.SetNthControlPointLabel(i, region+str(j+1))
            #         currentNode.SetNthControlPointDescription(i, defaultDescription)
            #         i += 1

            # activate persistent place mode for control points
            interactionNode = slicer.util.getNodesByClass("vtkMRMLInteractionNode")
            markupsLogic.StartPlaceMode(interactionNode)

            # ToDo:
            # Node List: SetDescription seems bugged and resets
            # register shortcuts for extra functionality in markups?

    def onLoadButton(self):
        """
        Establish the connection to an XNAT server with the provided user credentials.
        """
        with slicer.util.tryWithErrorDisplay("Failed to load data.",
                                             waitCursor=True):
            if self.ui.serverLineEdit.text == '':
                # use local file instead
                self._imageIterator = LocalFileIterator(self.ui.localFolderLineEdit.text)
                # initialize iterator
                iter(self._imageIterator)
                self._imageIterator.set_skip_annotated(self.ui.skipCheckBox.checked)
                # load first image
                self._next()
                self.onInitializeButton()
                
            else:
                # if self._xnat is None:
                # create xnat object
                self._imageIterator = SimpleXNAT(self.ui.serverLineEdit.text,
                                                 user=self.ui.userLineEdit.text,
                                                 pwd=self.ui.passwordLineEdit.text,
                                                 xml_query_file=self.ui.xmlLineEdit.text)

                                        # frames=self.ui.filterFramesLineEdit.text
                                        # subject_id=self.ui.filterSubjectLineEdit.text
                                        # series_descripiton=self.ui.filterSeriesLineEdit.text

                # initialize iterator
                iter(self._imageIterator)

                # instantiate the DICOM browser
                slicer.util.selectModule("DICOM")
                # switch back to current module
                if self.parent().name == "VertebraLocatorModuleWidget":
                    slicer.util.selectModule("VertebraLocator")
                else:
                    slicer.util.selectModule("Markups")
                # load first image
                self._next()
                self.onInitializeButton()

    def onConfirmButton(self):
        """
        Save and export markups to xnat, then load the next image if available
        when user clicks "Confirm | Next Image" button.
        """
        with slicer.util.tryWithErrorDisplay("Failed to save annotations.",
                                             waitCursor=True):

            # old way of creating one markup node per spinal region
            # # JSON version
            # mergedFile = os.path.join(self._folder, self._currentID + ".json")
            # files = []
            # for markup in ["C", "T", "L", "S"]:
            #     path = os.path.join(self._folder, self._currentID+"_"+markup+".json")
            #     files.append(path)
            #     slicer.util.saveNode(slicer.util.getNode(markup), path)
            # self.logic.mergeMarkupJSON(files, mergedFile)
            #
            # # CSV version
            # mergedFile = os.path.join(self._folder, self._currentID + ".csv")
            # markupsLogic = slicer.modules.markups.logic()
            # combined_csv = []
            # for markup in ["C", "T", "L", "S"]:
            #     path = os.path.join(self._folder, self._currentID+"_"+markup+".csv")
            #     markupsLogic.ExportControlPointsToCSV(slicer.util.getNode(markup), path)
            #
            #     with open(path, newline='') as file:
            #         reader = csv.reader(file)
            #         for i, row in enumerate(reader):
            #             print(i)
            #             if not markup == "C" and i==0:
            #                 continue
            #             print(row)
            #             combined_csv.append(row)
            #
            # with open(mergedFile, 'w', newline='') as file:
            #     writer = csv.writer(file)
            #     writer.writerows(combined_csv)
            # print(combined_csv)
            #
            # # upload merged annotations
            # self._xnat.upload_annotations(mergedFile)

            with TemporaryDirectory() as tmp_dir:
                annotation_path = os.path.join(tmp_dir, "vertebrae_annotation.json")
                slicer.util.saveNode(slicer.util.getNode("Vertebrae"), annotation_path)
                self._imageIterator.store_annotations(annotation_path)

            self._next()
            self.onInitializeButton()

    def onCancelButton(self):
        """
        Don't save annotations to XNAT, continue to next image.
        """
        with slicer.util.tryWithErrorDisplay("Failed to continue.",
                                             waitCursor=True):
            # ToDo: desirable to save tag in XNAT, that image was processed
            #  with no annotation to save
            self._next()
            self.onInitializeButton()

    def onLoadAnnotationButton(self):
        """
        Load existing annotations from the XNAT server into the Slicer scene.
        """
        # ToDo:
        with slicer.util.tryWithErrorDisplay("Failed to load annotations.",
                                             waitCursor=True):
            # delete current image to not litter the viewer
            if self._currentAnnotation is not None:
                slicer.mrmlScene.RemoveNode(slicer.util.getNode(self._currentAnnotation))

            self._currentAnnotation = self._imageIterator.load_annotation()

            # file = self._xnat.download_annotations()
            # markupsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode")
            # slicer.modules.markups.logic().ImportControlPointsFromCSV(markupsNode, file)
            # markupsNode = load_annotation()

    def _next(self):
        """
        Utility function to load and switch to the next image.
        """
        next(self._imageIterator)

        self.ui.buttonLoadAnnotation.enabled = self._imageIterator.has_annotation()

        # delete current image to not litter the viewer
        if self._currentImage is not None:
            slicer.mrmlScene.RemoveNode(slicer.util.getNode(self._currentImage))
        if self._currentAnnotation is not None:
            slicer.mrmlScene.RemoveNode(slicer.util.getNode(self._currentAnnotation))

        self._currentImage = self._imageIterator.load_volume()

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
        if not parameterNode.GetParameter("serverLineEdit"):
            parameterNode.SetParameter("serverLineEdit", "https://")

    def mergeMarkupJSON(self, files, mergedFilePath=None):
        """
        Merge Markup JSON files provided as a list of paths into a single file.
        This way, control points of separate lists will be merged into a single
        list and stay like that when directly loaded into Slicer. For splitting
        a merged file back into separate lists, see splitMarkupJSON().
        Can be used without GUI widget.
        :param files: a list of JSON file paths
        :param mergedFilePath: file path for the resulting merged JSON file

        :returns: the path to the JSON file containing the merged control points
        """
        # ToDo: Check for repeating names of control points from different lists
        # ToDo: Store additional information of the individual JSON files

        allControlPoints = []
        for file in files:
            with open(file) as json_file:
                data = json.load(json_file)
                if data['markups'][0]['type'] != "Fiducial":
                    raise ValueError("Input file is not a Fiducial type Markup")
                for controlPoint in data['markups'][0]['controlPoints']:
                    allControlPoints.append(controlPoint)

        # overwrite control points of last JSON to create merged markup
        data['markups'][0]['controlPoints'] = allControlPoints

        # store merged file
        if mergedFilePath is None:
            mergedFilePath = os.path.join(os.path.dirname(files[-1]),
                                          files[-1].rpartition('_')[0] + '_merged.json')
        with open(mergedFilePath, 'w') as outfile:
            json.dump(data, outfile, indent=4)
        return mergedFilePath

    def splitMarkupJSON(self, file, splitFiles=None):
        """
        Split a Markup JSON file into multiple files, based on the control
        point names. Splitting into C, T, L, and S vertebral regions.

        :param file: path to a file which is to be split
        :param splitFiles: a list of paths for the resulting split JSON files
        :return: a list of paths to files with the split annotation files
        """
        cControlPoints = []
        tControlPoints = []
        lControlPoints = []
        sControlPoints = []
        with open(file) as json_file:
            data = json.load(json_file)
            if data['markups'][0]['type'] != "Fiducial":
                raise ValueError("Input file is not a Fiducial type Markup")
            for controlPoint in data['markups'][0]['controlPoints']:
                if controlPoint['label'].startswith("C"):
                    cControlPoints.append(controlPoint)
                if controlPoint['label'].startswith("T"):
                    tControlPoints.append(controlPoint)
                if controlPoint['label'].startswith("L"):
                    lControlPoints.append(controlPoint)
                if controlPoint['label'].startswith("S"):
                    sControlPoints.append(controlPoint)
        allData = [deepcopy(data) for _ in range(4)]
        allData[0]['markups'][0]['controlPoints'] = cControlPoints
        allData[1]['markups'][0]['controlPoints'] = tControlPoints
        allData[2]['markups'][0]['controlPoints'] = lControlPoints
        allData[3]['markups'][0]['controlPoints'] = sControlPoints

        # ToDo: recover additional markup data stored in the merged file

        # store split files
        if splitFiles is None:
            creatingResultPaths = True
            splitFiles = []
            for i, section in enumerate(["C", "T", "L", "S"]):
                if creatingResultPaths:
                    path = os.path.join(file.rpartition('.')[0]+'_test_'+section+'.json')
                    print(path)
                    splitFiles.append(path)

                with open(splitFiles[i], 'w') as outfile:
                    json.dump(allData[i], outfile, indent=4)

        return splitFiles


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
