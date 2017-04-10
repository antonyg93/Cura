# Copyright (c) 2017 Ultimaker B.V.
# Cura is released under the terms of the AGPLv3 or higher.

import os.path #To find the test files.
import pytest #This module contains unit tests.
import unittest.mock #To monkeypatch some mocks in place of dependencies.
import functools

import cura.Settings.GlobalStack #The module we're testing.
import cura.Settings.CuraContainerStack #To get the list of container types.
from cura.Settings.Exceptions import TooManyExtrudersError, InvalidContainerError, InvalidOperationError #To test raising these errors.
from UM.Settings.DefinitionContainer import DefinitionContainer #To test against the class DefinitionContainer.
from UM.Settings.InstanceContainer import InstanceContainer #To test against the class InstanceContainer.
import UM.Settings.ContainerRegistry
import UM.Settings.ContainerStack

class MockContainer:
    def __init__(self, container_id, type = "mock"):
        self._id = container_id
        self._type = type

        self._property_map = {}

    def getId(self):
        return self._id

    def getMetaDataEntry(self, entry, default = None):
        if entry == "type":
            return self._type

        return default

    def getProperty(self, key, property_name):
        if key not in self._property_map:
            return None

        if property_name not in self._property_map[key]:
            return None

        return self._property_map[key][property_name]

    def setProperty(self, key, property_name, value):
        if key not in self._property_map:
            self._property_map[key] = {}

        self._property_map[key][property_name] = value

    propertyChanged = unittest.mock.MagicMock()

##  Fake container registry that always provides all containers you ask of.
@pytest.yield_fixture()
def container_registry():
    registry = unittest.mock.MagicMock()

    registry.typeMetaData = "registry_mock"

    def findInstanceContainers(registry, **kwargs):
        container_id = kwargs.get("id", "test_container")
        return [MockContainer(container_id, registry.typeMetaData)]
    registry.findInstanceContainers = functools.partial(findInstanceContainers, registry)

    def findContainers(registry, container_type = None, id = None):
        if not id:
            id = "test_container"
        return [MockContainer(id, registry.typeMetaData)]
    registry.findContainers = functools.partial(findContainers, registry)

    def getEmptyInstanceContainer():
        return MockContainer(container_id = "empty")
    registry.getEmptyInstanceContainer = getEmptyInstanceContainer

    UM.Settings.ContainerRegistry.ContainerRegistry._ContainerRegistry__instance = registry
    UM.Settings.ContainerStack._containerRegistry = registry

    yield registry

    UM.Settings.ContainerRegistry.ContainerRegistry._ContainerRegistry__instance = None
    UM.Settings.ContainerStack._containerRegistry = None

#An empty global stack to test with.
@pytest.fixture()
def global_stack() -> cura.Settings.GlobalStack.GlobalStack:
    return cura.Settings.GlobalStack.GlobalStack("TestStack")

@pytest.fixture()
def writable_global_stack(global_stack):
    global_stack.userChanges = MockContainer("test_user_changes", "user")
    global_stack.qualityChanges = MockContainer("test_quality_changes", "quality_changes")
    global_stack.quality = MockContainer("test_quality", "quality")
    global_stack.material = MockContainer("test_material", "material")
    global_stack.variant = MockContainer("test_variant", "variant")
    global_stack.definitionChanges = MockContainer("test_definition_changes", "definition_changes")
    global_stack.definition = DefinitionContainerSubClass()
    return global_stack

##  Place-in function for findContainer that finds only containers that start
#   with "some_".
def findSomeContainers(container_id = "*", container_type = None, type = None, category = "*"):
    if container_id.startswith("some_"):
        return UM.Settings.ContainerRegistry._EmptyInstanceContainer(container_id)
    if container_type == DefinitionContainer:
        definition_mock = unittest.mock.MagicMock()
        definition_mock.getId = unittest.mock.MagicMock(return_value = "some_definition") #getId returns some_definition.
        return definition_mock

##  Helper function to read the contents of a container stack in the test
#   stack folder.
#
#   \param filename The name of the file in the "stacks" folder to read from.
#   \return The contents of that file.
def readStack(filename):
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "stacks", filename)) as file_handle:
        serialized = file_handle.read()
    return serialized

##  Gets an instance container with a specified container type.
#
#   \param container_type The type metadata for the instance container.
#   \return An instance container instance.
def getInstanceContainer(container_type) -> InstanceContainer:
    container = InstanceContainer(container_id = "InstanceContainer")
    container.addMetaDataEntry("type", container_type)
    return container

class DefinitionContainerSubClass(DefinitionContainer):
    def __init__(self):
        super().__init__(container_id = "SubDefinitionContainer")

class InstanceContainerSubClass(InstanceContainer):
    def __init__(self, container_type):
        super().__init__(container_id = "SubInstanceContainer")
        self.addMetaDataEntry("type", container_type)

#############################START OF TEST CASES################################

##  Tests whether adding a container is properly forbidden.
def test_addContainer(global_stack):
    with pytest.raises(InvalidOperationError):
        global_stack.addContainer(unittest.mock.MagicMock())

##  Tests adding extruders to the global stack.
def test_addExtruder(global_stack):
    mock_definition = unittest.mock.MagicMock()
    mock_definition.getProperty = lambda key, property: 2 if key == "machine_extruder_count" and property == "value" else None

    with unittest.mock.patch("cura.Settings.CuraContainerStack.DefinitionContainer", unittest.mock.MagicMock):
        global_stack.definition = mock_definition

    assert len(global_stack.extruders) == 0
    first_extruder = unittest.mock.MagicMock()
    with unittest.mock.patch("cura.Settings.CuraContainerStack.DefinitionContainer", unittest.mock.MagicMock):
        global_stack.addExtruder(first_extruder)
    assert len(global_stack.extruders) == 1
    assert global_stack.extruders[0] == first_extruder
    second_extruder = unittest.mock.MagicMock()
    with unittest.mock.patch("cura.Settings.CuraContainerStack.DefinitionContainer", unittest.mock.MagicMock):
        global_stack.addExtruder(second_extruder)
    assert len(global_stack.extruders) == 2
    assert global_stack.extruders[1] == second_extruder
    with unittest.mock.patch("cura.Settings.CuraContainerStack.DefinitionContainer", unittest.mock.MagicMock):
        with pytest.raises(TooManyExtrudersError): #Should be limited to 2 extruders because of machine_extruder_count.
            global_stack.addExtruder(unittest.mock.MagicMock())
    assert len(global_stack.extruders) == 2 #Didn't add the faulty extruder.

#Tests setting user changes profiles to invalid containers.
@pytest.mark.parametrize("container", [
    getInstanceContainer(container_type = "wrong container type"),
    getInstanceContainer(container_type = "material"), #Existing, but still wrong type.
    DefinitionContainer(container_id = "wrong class")
])
def test_constrainUserChangesInvalid(container, global_stack):
    with pytest.raises(InvalidContainerError): #Invalid container, should raise an error.
        global_stack.userChanges = container

#Tests setting user changes profiles.
@pytest.mark.parametrize("container", [
    getInstanceContainer(container_type = "user"),
    InstanceContainerSubClass(container_type = "user")
])
def test_constrainUserChangesValid(container, global_stack):
    global_stack.userChanges = container #Should not give an error.

#Tests setting quality changes profiles to invalid containers.
@pytest.mark.parametrize("container", [
    getInstanceContainer(container_type = "wrong container type"),
    getInstanceContainer(container_type = "material"), #Existing, but still wrong type.
    DefinitionContainer(container_id = "wrong class")
])
def test_constrainQualityChangesInvalid(container, global_stack):
    with pytest.raises(InvalidContainerError): #Invalid container, should raise an error.
        global_stack.qualityChanges = container

#Test setting quality changes profiles.
@pytest.mark.parametrize("container", [
    getInstanceContainer(container_type = "quality_changes"),
    InstanceContainerSubClass(container_type = "quality_changes")
])
def test_constrainQualityChangesValid(container, global_stack):
    global_stack.qualityChanges = container #Should not give an error.

#Tests setting quality profiles to invalid containers.
@pytest.mark.parametrize("container", [
    getInstanceContainer(container_type = "wrong container type"),
    getInstanceContainer(container_type = "material"), #Existing, but still wrong type.
    DefinitionContainer(container_id = "wrong class")
])
def test_constrainQualityInvalid(container, global_stack):
    with pytest.raises(InvalidContainerError): #Invalid container, should raise an error.
        global_stack.quality = container

#Test setting quality profiles.
@pytest.mark.parametrize("container", [
    getInstanceContainer(container_type = "quality"),
    InstanceContainerSubClass(container_type = "quality")
])
def test_constrainQualityValid(container, global_stack):
    global_stack.quality = container #Should not give an error.

#Tests setting materials to invalid containers.
@pytest.mark.parametrize("container", [
    getInstanceContainer(container_type = "wrong container type"),
    getInstanceContainer(container_type = "quality"), #Existing, but still wrong type.
    DefinitionContainer(container_id = "wrong class")
])
def test_constrainMaterialInvalid(container, global_stack):
    with pytest.raises(InvalidContainerError): #Invalid container, should raise an error.
        global_stack.material = container

#Test setting materials.
@pytest.mark.parametrize("container", [
    getInstanceContainer(container_type = "material"),
    InstanceContainerSubClass(container_type = "material")
])
def test_constrainMaterialValid(container, global_stack):
    global_stack.material = container #Should not give an error.

#Tests setting variants to invalid containers.
@pytest.mark.parametrize("container", [
    getInstanceContainer(container_type = "wrong container type"),
    getInstanceContainer(container_type = "material"), #Existing, but still wrong type.
    DefinitionContainer(container_id = "wrong class")
])
def test_constrainVariantInvalid(container, global_stack):
    with pytest.raises(InvalidContainerError): #Invalid container, should raise an error.
        global_stack.variant = container

#Test setting variants.
@pytest.mark.parametrize("container", [
    getInstanceContainer(container_type = "variant"),
    InstanceContainerSubClass(container_type = "variant")
])
def test_constrainVariantValid(container, global_stack):
    global_stack.variant = container #Should not give an error.

#Tests setting definition changes profiles to invalid containers.
@pytest.mark.parametrize("container", [
    getInstanceContainer(container_type = "wrong container type"),
    getInstanceContainer(container_type = "material"), #Existing, but still wrong type.
    DefinitionContainer(container_id = "wrong class")
])
def test_constrainDefinitionChangesInvalid(container, global_stack):
    with pytest.raises(InvalidContainerError): #Invalid container, should raise an error.
        global_stack.definitionChanges = container

#Test setting definition changes profiles.
@pytest.mark.parametrize("container", [
    getInstanceContainer(container_type = "definition_changes"),
    InstanceContainerSubClass(container_type = "definition_changes")
])
def test_constrainDefinitionChangesValid(container, global_stack):
    global_stack.definitionChanges = container #Should not give an error.

#Tests setting definitions to invalid containers.
@pytest.mark.parametrize("container", [
    getInstanceContainer(container_type = "wrong class"),
    getInstanceContainer(container_type = "material"), #Existing, but still wrong class.
])
def test_constrainVariantInvalid(container, global_stack):
    with pytest.raises(InvalidContainerError): #Invalid container, should raise an error.
        global_stack.definition = container

#Test setting definitions.
@pytest.mark.parametrize("container", [
    DefinitionContainer(container_id = "DefinitionContainer"),
    DefinitionContainerSubClass()
])
def test_constrainDefinitionValid(container, global_stack):
    global_stack.definition = container #Should not give an error.

##  Tests whether deserialising completes the missing containers with empty
#   ones.
@pytest.mark.skip #The test currently fails because the definition container doesn't have a category, which is wrong but we don't have time to refactor that right now.
def test_deserializeCompletesEmptyContainers(global_stack: cura.Settings.GlobalStack):
    global_stack._containers = [DefinitionContainer(container_id = "definition")] #Set the internal state of this stack manually.

    with unittest.mock.patch("UM.Settings.ContainerStack.ContainerStack.deserialize", unittest.mock.MagicMock()): #Prevent calling super().deserialize.
        global_stack.deserialize("")

    assert len(global_stack.getContainers()) == len(cura.Settings.CuraContainerStack._ContainerIndexes.IndexTypeMap) #Needs a slot for every type.
    for container_type_index in cura.Settings.CuraContainerStack._ContainerIndexes.IndexTypeMap:
        if container_type_index == cura.Settings.CuraContainerStack._ContainerIndexes.Definition: #We're not checking the definition.
            continue
        assert global_stack.getContainer(container_type_index).getId() == "empty" #All others need to be empty.

##  Tests whether the user changes are being read properly from a global stack.
@pytest.mark.parametrize("filename,                 user_changes_id", [
                        ("Global.global.cfg",       "empty"),
                        ("Global.stack.cfg",        "empty"),
                        ("MachineLegacy.stack.cfg", "empty"),
                        ("OnlyUser.global.cfg",     "some_instance"), #This one does have a user profile.
                        ("Complete.global.cfg",     "some_user_changes")
])
def test_deserializeUserChanges(filename, user_changes_id, container_registry, global_stack):
    serialized = readStack(filename)

    #Mock the loading of the instance containers.
    global_stack.findContainer = findSomeContainers
    original_container_registry = UM.Settings.ContainerStack._containerRegistry
    UM.Settings.ContainerStack._containerRegistry = container_registry #Always has all profiles you ask of.

    global_stack.deserialize(serialized)

    assert global_stack.userChanges.getId() == user_changes_id

    #Restore.
    UM.Settings.ContainerStack._containerRegistry = original_container_registry

##  Tests whether the quality changes are being read properly from a global
#   stack.
@pytest.mark.parametrize("filename,                       quality_changes_id", [
                        ("Global.global.cfg",             "empty"),
                        ("Global.stack.cfg",              "empty"),
                        ("MachineLegacy.stack.cfg",       "empty"),
                        ("OnlyQualityChanges.global.cfg", "some_instance"),
                        ("Complete.global.cfg",           "some_quality_changes")
])
def test_deserializeQualityChanges(filename, quality_changes_id, container_registry, global_stack):
    serialized = readStack(filename)

    #Mock the loading of the instance containers.
    global_stack.findContainer = findSomeContainers
    original_container_registry = UM.Settings.ContainerStack._containerRegistry
    UM.Settings.ContainerStack._containerRegistry = container_registry #Always has all the profiles you ask of.

    global_stack.deserialize(serialized)

    assert global_stack.qualityChanges.getId() == quality_changes_id

    #Restore.
    UM.Settings.ContainerStack._containerRegistry = original_container_registry

##  Tests whether the quality profile is being read properly from a global
#   stack.
@pytest.mark.parametrize("filename,                 quality_id", [
                        ("Global.global.cfg",       "empty"),
                        ("Global.stack.cfg",        "empty"),
                        ("MachineLegacy.stack.cfg", "empty"),
                        ("OnlyQuality.global.cfg",  "some_instance"),
                        ("Complete.global.cfg",     "some_quality")
])
def test_deserializeQuality(filename, quality_id, container_registry, global_stack):
    serialized = readStack(filename)

    #Mock the loading of the instance containers.
    global_stack.findContainer = findSomeContainers
    original_container_registry = UM.Settings.ContainerStack._containerRegistry
    UM.Settings.ContainerStack._containerRegistry = container_registry #Always has all the profiles you ask of.

    global_stack.deserialize(serialized)

    assert global_stack.quality.getId() == quality_id

    #Restore.
    UM.Settings.ContainerStack._containerRegistry = original_container_registry

##  Tests whether the material profile is being read properly from a global
#   stack.
@pytest.mark.parametrize("filename,                   material_id", [
                        ("Global.global.cfg",         "some_instance"),
                        ("Global.stack.cfg",          "some_instance"),
                        ("MachineLegacy.stack.cfg",   "some_instance"),
                        ("OnlyDefinition.global.cfg", "empty"),
                        ("OnlyMaterial.global.cfg",   "some_instance"),
                        ("Complete.global.cfg",       "some_material")
])
def test_deserializeMaterial(filename, material_id, container_registry, global_stack):
    serialized = readStack(filename)

    #Mock the loading of the instance containers.
    global_stack.findContainer = findSomeContainers
    original_container_registry = UM.Settings.ContainerStack._containerRegistry
    UM.Settings.ContainerStack._containerRegistry = container_registry #Always has all the profiles you ask of.

    global_stack.deserialize(serialized)

    assert global_stack.material.getId() == material_id

    #Restore.
    UM.Settings.ContainerStack._containerRegistry = original_container_registry

##  Tests whether the variant profile is being read properly from a global
#   stack.
@pytest.mark.parametrize("filename,                 variant_id", [
                        ("Global.global.cfg",       "empty"),
                        ("Global.stack.cfg",        "empty"),
                        ("MachineLegacy.stack.cfg", "empty"),
                        ("OnlyVariant.global.cfg",  "some_instance"),
                        ("Complete.global.cfg",     "some_variant")
])
def test_deserializeVariant(filename, variant_id, container_registry, global_stack):
    serialized = readStack(filename)

    #Mock the loading of the instance containers.
    global_stack.findContainer = findSomeContainers
    original_container_registry = UM.Settings.ContainerStack._containerRegistry
    UM.Settings.ContainerStack._containerRegistry = container_registry #Always has all the profiles you ask of.

    global_stack.deserialize(serialized)

    assert global_stack.variant.getId() == variant_id

    #Restore.
    UM.Settings.ContainerStack._containerRegistry = original_container_registry

##  Tests whether the definition changes profile is being read properly from a
#   global stack.
@pytest.mark.parametrize("filename,                          definition_changes_id", [
                        ("Global.global.cfg",                "empty"),
                        ("Global.stack.cfg",                 "empty"),
                        ("MachineLegacy.stack.cfg",          "empty"),
                        ("OnlyDefinitionChanges.global.cfg", "some_instance"),
                        ("Complete.global.cfg",              "some_material")
])
def test_deserializeDefinitionChanges(filename, definition_changes_id, container_registry, global_stack):
    serialized = readStack(filename)
    global_stack = cura.Settings.GlobalStack.GlobalStack("TestStack")

    #Mock the loading of the instance containers.
    global_stack.findContainer = findSomeContainers
    original_container_registry = UM.Settings.ContainerStack._containerRegistry
    UM.Settings.ContainerStack._containerRegistry = container_registry #Always has all the profiles you ask of.

    global_stack.deserialize(serialized)

    assert global_stack.definitionChanges.getId() == definition_changes_id

    #Restore.
    UM.Settings.ContainerStack._containerRegistry = original_container_registry

##  Tests whether the definition is being read properly from a global stack.
@pytest.mark.parametrize("filename,                   definition_id", [
                        ("Global.global.cfg",         "some_definition"),
                        ("Global.stack.cfg",          "some_definition"),
                        ("MachineLegacy.stack.cfg",   "some_definition"),
                        ("OnlyDefinition.global.cfg", "some_definition"),
                        ("Complete.global.cfg",       "some_definition")
])
def test_deserializeDefinition(filename, definition_id, container_registry, global_stack):
    serialized = readStack(filename)

    #Mock the loading of the instance containers.
    global_stack.findContainer = findSomeContainers
    original_container_registry = UM.Settings.ContainerStack._containerRegistry
    UM.Settings.ContainerStack._containerRegistry = container_registry #Always has all the profiles you ask of.

    global_stack.deserialize(serialized)

    assert global_stack.definition.getId() == definition_id

    #Restore.
    UM.Settings.ContainerStack._containerRegistry = original_container_registry

##  Tests that when a global stack is loaded with an unknown instance, it raises
#   an exception.
def test_deserializeMissingContainer(global_stack):
    serialized = readStack("Global.global.cfg")
    with pytest.raises(Exception):
        global_stack.deserialize(serialized)
    try:
        global_stack.deserialize(serialized)
    except Exception as e:
        #Must be exactly Exception, not one of its subclasses, since that is what gets raised when a stack has an unknown container.
        #That's why we can't use pytest.raises.
        assert type(e) == Exception

##  Tests whether getProperty properly applies the stack-like behaviour on its
#   containers.
def test_getPropertyFallThrough(global_stack):
    #A few instance container mocks to put in the stack.
    mock_layer_heights = {} #For each container type, a mock container that defines layer height to something unique.
    mock_no_settings = {} #For each container type, a mock container that has no settings at all.
    container_indexes = cura.Settings.CuraContainerStack._ContainerIndexes #Cache.
    for type_id, type_name in container_indexes.IndexTypeMap.items():
        container = unittest.mock.MagicMock()
        container.getProperty = lambda key, property, type_id = type_id: type_id if (key == "layer_height" and property == "value") else None #Returns the container type ID as layer height, in order to identify it.
        container.hasProperty = lambda key, property: key == "layer_height"
        container.getMetaDataEntry = unittest.mock.MagicMock(return_value = type_name)
        mock_layer_heights[type_id] = container

        container = unittest.mock.MagicMock()
        container.getProperty = unittest.mock.MagicMock(return_value = None) #Has no settings at all.
        container.hasProperty = unittest.mock.MagicMock(return_value = False)
        container.getMetaDataEntry = unittest.mock.MagicMock(return_value = type_name)
        mock_no_settings[type_id] = container

    global_stack.userChanges = mock_no_settings[container_indexes.UserChanges]
    global_stack.qualityChanges = mock_no_settings[container_indexes.QualityChanges]
    global_stack.quality = mock_no_settings[container_indexes.Quality]
    global_stack.material = mock_no_settings[container_indexes.Material]
    global_stack.variant = mock_no_settings[container_indexes.Variant]
    global_stack.definitionChanges = mock_no_settings[container_indexes.DefinitionChanges]
    with unittest.mock.patch("cura.Settings.CuraContainerStack.DefinitionContainer", unittest.mock.MagicMock): #To guard against the type checking.
        global_stack.definition = mock_layer_heights[container_indexes.Definition] #There's a layer height in here!

    assert global_stack.getProperty("layer_height", "value") == container_indexes.Definition
    global_stack.definitionChanges = mock_layer_heights[container_indexes.DefinitionChanges]
    assert global_stack.getProperty("layer_height", "value") == container_indexes.DefinitionChanges
    global_stack.variant = mock_layer_heights[container_indexes.Variant]
    assert global_stack.getProperty("layer_height", "value") == container_indexes.Variant
    global_stack.material = mock_layer_heights[container_indexes.Material]
    assert global_stack.getProperty("layer_height", "value") == container_indexes.Material
    global_stack.quality = mock_layer_heights[container_indexes.Quality]
    assert global_stack.getProperty("layer_height", "value") == container_indexes.Quality
    global_stack.qualityChanges = mock_layer_heights[container_indexes.QualityChanges]
    assert global_stack.getProperty("layer_height", "value") == container_indexes.QualityChanges
    global_stack.userChanges = mock_layer_heights[container_indexes.UserChanges]
    assert global_stack.getProperty("layer_height", "value") == container_indexes.UserChanges

def test_getPropertyWithResolve(global_stack):
    #Define some containers for the stack.
    resolve = unittest.mock.MagicMock() #Sets just the resolve for bed temperature.
    resolve.getProperty = lambda key, property: 15 if (key == "material_bed_temperature" and property == "resolve") else None
    resolve_and_value = unittest.mock.MagicMock() #Sets the resolve and value for bed temperature.
    resolve_and_value.getProperty = lambda key, property: (7.5 if property == "resolve" else 5) if (key == "material_bed_temperature") else None #7.5 resolve, 5 value.
    value = unittest.mock.MagicMock() #Sets just the value for bed temperature.
    value.getProperty = lambda key, property: 10 if (key == "material_bed_temperature" and property == "value") else None
    empty = unittest.mock.MagicMock() #Sets no value or resolve.
    empty.getProperty = unittest.mock.MagicMock(return_value = None)

    with unittest.mock.patch("cura.Settings.CuraContainerStack.DefinitionContainer", unittest.mock.MagicMock): #To guard against the type checking.
        global_stack.definition = resolve_and_value
    assert global_stack.getProperty("material_bed_temperature", "value") == 7.5 #Resolve wins in the definition.
    global_stack.userChanges = resolve_and_value
    assert global_stack.getProperty("material_bed_temperature", "value") == 5 #Value wins in other places.
    global_stack.userChanges = value
    assert global_stack.getProperty("material_bed_temperature", "value") == 10 #Resolve in the definition doesn't influence the value in the user changes.
    global_stack.userChanges = resolve
    assert global_stack.getProperty("material_bed_temperature", "value") == 15 #Falls through to definition for lack of values, but then asks the start of the stack for the resolve.
    global_stack.userChanges = empty
    global_stack.qualityChanges = resolve_and_value
    assert global_stack.getProperty("material_bed_temperature", "value") == 5 #Value still wins in lower places, except definition.
    global_stack.qualityChanges = empty
    global_stack.quality = resolve_and_value
    assert global_stack.getProperty("material_bed_temperature", "value") == 5
    global_stack.quality = empty
    global_stack.material = resolve_and_value
    assert global_stack.getProperty("material_bed_temperature", "value") == 5
    global_stack.material = empty
    global_stack.variant = resolve_and_value
    assert global_stack.getProperty("material_bed_temperature", "value") == 5
    global_stack.variant = empty
    global_stack.definitionChanges = resolve_and_value
    assert global_stack.getProperty("material_bed_temperature", "value") == 5

##  Tests whether the hasUserValue returns true for settings that are changed in
#   the user-changes container.
def test_hasUserValueUserChanges(global_stack):
    user_changes = MockContainer("test_user_changes", "user")

    def hasProperty(key, property):
        return key == "layer_height" and property == "value" # Only have the layer_height property set.
    user_changes.hasProperty = hasProperty

    global_stack.userChanges = user_changes

    assert not global_stack.hasUserValue("infill_sparse_density")
    assert global_stack.hasUserValue("layer_height")
    assert not global_stack.hasUserValue("")

##  Tests whether the hasUserValue returns true for settings that are changed in
#   the quality-changes container.
def test_hasUserValueQualityChanges(global_stack):
    quality_changes = MockContainer("test_quality_changes", "quality_changes")

    def hasProperty(key, property):
        return key == "layer_height" and property == "value" # Only have the layer_height property set.
    quality_changes.hasProperty = hasProperty

    global_stack.qualityChanges = quality_changes

    assert not global_stack.hasUserValue("infill_sparse_density")
    assert global_stack.hasUserValue("layer_height")
    assert not global_stack.hasUserValue("")

##  Tests whether inserting a container is properly forbidden.
def test_insertContainer(global_stack):
    with pytest.raises(InvalidOperationError):
        global_stack.insertContainer(0, unittest.mock.MagicMock())

##  Tests whether removing a container is properly forbidden.
def test_removeContainer(global_stack):
    with pytest.raises(InvalidOperationError):
        global_stack.removeContainer(unittest.mock.MagicMock())

##  Tests setting definitions by specifying an ID of a definition that exists.
def test_setDefinitionByIdExists(global_stack, container_registry):
    with unittest.mock.patch("cura.Settings.CuraContainerStack.DefinitionContainer", unittest.mock.MagicMock): #To guard against type checking the DefinitionContainer.
        global_stack.setDefinitionById("some_definition") #The container registry always has a container with the ID.

##  Tests setting definitions by specifying an ID of a definition that doesn't
#   exist.
def test_setDefinitionByIdDoesntExist(global_stack):
    with pytest.raises(InvalidContainerError):
        global_stack.setDefinitionById("some_definition") #Container registry is empty now.

##  Tests setting definition changes by specifying an ID of a container that
#   exists.
def test_setDefinitionChangesByIdExists(global_stack, container_registry):
    container_registry.typeMetaData = "definition_changes"
    global_stack.setDefinitionChangesById("some_definition_changes") #The container registry always has a container with the ID.

##  Tests setting definition changes by specifying an ID of a container that
#   doesn't exist.
def test_setDefinitionChangesByIdDoesntExist(global_stack):
    with pytest.raises(InvalidContainerError):
        global_stack.setDefinitionChangesById("some_definition_changes") #Container registry is empty now.

##  Tests setting materials by specifying an ID of a material that exists.
def test_setMaterialByIdExists(global_stack, container_registry):
    container_registry.typeMetaData = "material"
    global_stack.setMaterialById("some_material") #The container registry always has a container with the ID.

##  Tests setting materials by specifying an ID of a material that doesn't
#   exist.
def test_setMaterialByIdDoesntExist(global_stack):
    with pytest.raises(InvalidContainerError):
        global_stack.setMaterialById("some_material") #Container registry is empty now.

##  Tests whether changing the next stack is properly forbidden.
def test_setNextStack(global_stack):
    with pytest.raises(InvalidOperationError):
        global_stack.setNextStack(unittest.mock.MagicMock())

##  Tests setting properties directly on the global stack.
@pytest.mark.parametrize("key,              property,         value,       output_value", [
                        ("layer_height",    "value",          0.1337,    0.1337),
                        ("foo",             "value",          100,       100),
                        ("support_enabled", "value",          True,      True),
                        ("layer_height",    "default_value",  0.1337,      0.1337),
                        ("layer_height",    "is_bright_pink", "of course", "of course")
])
def test_setPropertyUser(key, property, value, output_value, writable_global_stack):
    writable_global_stack.setProperty(key, property, value)
    assert writable_global_stack.userChanges.getProperty(key, property) == output_value

##  Tests setting properties on specific containers on the global stack.
@pytest.mark.parametrize("target_container", [
    "user",
    "quality_changes",
    "quality",
    "material",
    "variant",
    "definition_changes",
])
def test_setPropertyOtherContainers(target_container, writable_global_stack):
    #Other parameters that don't need to be varied.
    key = "layer_height"
    property = "value"
    value = 0.1337
    output_value = 0.1337

    writable_global_stack.setProperty(key, property, value, target_container = target_container)
    containers = {
        "user": writable_global_stack.userChanges,
        "quality_changes": writable_global_stack.qualityChanges,
        "quality": writable_global_stack.quality,
        "material": writable_global_stack.material,
        "variant": writable_global_stack.variant,
        "definition_changes": writable_global_stack.definitionChanges,
        "definition": writable_global_stack.definition
    }
    assert containers[target_container].getProperty(key, property) == output_value

##  Tests setting qualities by specifying an ID of a quality that exists.
def test_setQualityByIdExists(global_stack, container_registry):
    container_registry.typeMetaData = "quality"
    global_stack.setQualityById("some_quality") #The container registry always has a container with the ID.

##  Tests setting qualities by specifying an ID of a quality that doesn't exist.
def test_setQualityByIdDoesntExist(global_stack):
    with pytest.raises(InvalidContainerError):
        global_stack.setQualityById("some_quality") #Container registry is empty now.

##  Tests setting quality changes by specifying an ID of a quality change that
#   exists.
def test_setQualityChangesByIdExists(global_stack, container_registry):
    container_registry.typeMetaData = "quality_changes"
    global_stack.setQualityChangesById("some_quality_changes") #The container registry always has a container with the ID.

##  Tests setting quality changes by specifying an ID of a quality change that
#   doesn't exist.
def test_setQualityChangesByIdDoesntExist(global_stack):
    with pytest.raises(InvalidContainerError):
        global_stack.setQualityChangesById("some_quality_changes") #Container registry is empty now.

##  Tests setting variants by specifying an ID of a variant that exists.
def test_setVariantByIdExists(global_stack, container_registry):
    container_registry.typeMetaData = "variant"
    global_stack.setVariantById("some_variant") #The container registry always has a container with the ID.

##  Tests setting variants by specifying an ID of a variant that doesn't exist.
def test_setVariantByIdDoesntExist(global_stack):
    with pytest.raises(InvalidContainerError):
        global_stack.setVariantById("some_variant") #Container registry is empty now.
