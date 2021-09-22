from typing import Dict, Text

from zenml.artifact_stores.base_artifact_store import BaseArtifactStore
from zenml.core import mapping_utils
from zenml.core.base_component import BaseComponent
from zenml.core.mapping_utils import UUIDSourceTuple
from zenml.exceptions import AlreadyExistsException, DoesNotExistException
from zenml.logger import get_logger
from zenml.metadata.base_metadata_store import BaseMetadataStore
from zenml.orchestrators.base_orchestrator import BaseOrchestrator
from zenml.providers.base_provider import BaseProvider
from zenml.utils import path_utils, source_utils

logger = get_logger(__name__)


class LocalService(BaseComponent):
    """Definition of a local service that keeps track of all ZenML
    components.
    """

    providers: Dict[Text, BaseProvider] = {}
    metadata_store_map: Dict[Text, UUIDSourceTuple] = {}
    artifact_store_map: Dict[Text, UUIDSourceTuple] = {}
    orchestrator_map: Dict[Text, UUIDSourceTuple] = {}

    _LOCAL_SERVICE_FILE_NAME = "zenservice.json"

    def get_serialization_dir(self) -> Text:
        """The local service stores everything in the zenml config dir."""
        return path_utils.get_zenml_config_dir()

    def get_serialization_file_name(self) -> Text:
        """Return the name of the file where object is serialized."""
        return self._LOCAL_SERVICE_FILE_NAME

    @property
    def metadata_stores(self) -> Dict[Text, BaseMetadataStore]:
        """Returns all registered metadata stores."""
        return mapping_utils.get_components_from_store(
            BaseMetadataStore._METADATA_STORE_DIR_NAME, self.metadata_store_map
        )

    @property
    def artifact_stores(self) -> Dict[Text, BaseArtifactStore]:
        """Returns all registered artifact stores."""
        return mapping_utils.get_components_from_store(
            BaseArtifactStore._ARTIFACT_STORE_DIR_NAME, self.artifact_store_map
        )

    @property
    def orchestrators(self) -> Dict[Text, BaseOrchestrator]:
        """Returns all registered orchestrators."""
        return mapping_utils.get_components_from_store(
            BaseOrchestrator._ORCHESTRATOR_STORE_DIR_NAME,
            self.orchestrator_map,
        )

    def get_provider(self, key: Text) -> BaseProvider:
        """Return a single provider based on key.

        Args:
            key: Unique key of provider.

        Returns:
            Provider specified by key.
        """
        logger.debug(f"Fetching provider with key {key}")
        if key not in self.providers:
            raise DoesNotExistException(
                f"Provider of key `{key}` does not exist. "
                f"Available keys: {self.providers.keys()}"
            )
        return self.providers[key]

    def register_provider(self, key: Text, provider: BaseProvider):
        """Register a provider.

        Args:
            key: Unique key for the provider.
            provider: Provider to be registered.
        """
        logger.info(
            f"Registering provider with key {key}, details: "
            f"{provider.dict()}"
        )

        if key in self.providers:
            raise AlreadyExistsException(
                message=f"Provider `{key}` already exists!"
            )

        # Add the mapping.
        self.providers[key] = provider
        self.update()

    def delete_provider(self, key: Text):
        """Delete a provider specified with a key.

        Args:
            key: Unique key of provider.
        """
        _ = self.get_provider(key)  # check whether it exists
        del self.providers[key]
        self.update()
        logger.info(f"Deleted provider with key: {key}.")

    def get_artifact_store(self, key: Text) -> BaseArtifactStore:
        """Return a single artifact store based on key.

        Args:
            key: Unique key of artifact store.

        Returns:
            Provider specified by key.
        """
        logger.debug(f"Fetching artifact_store with key {key}")
        if key not in self.artifact_store_map:
            raise DoesNotExistException(
                f"Provider of key `{key}` does not exist. "
                f"Available keys: {self.artifact_store_map.keys()}"
            )
        return mapping_utils.get_component_from_key(
            key, self.artifact_store_map
        )

    def register_artifact_store(
        self, key: Text, artifact_store: BaseArtifactStore
    ):
        """Register an artifact store.

        Args:
            artifact_store: Artifact store to be registered.
            key: Unique key for the artifact store.
        """
        logger.info(
            f"Registering provider with key {key}, details: "
            f"{artifact_store.dict()}"
        )
        if key in self.artifact_store_map:
            raise AlreadyExistsException(
                message=f"Artifact Store `{key}` already exists!"
            )

        # Add the mapping.
        artifact_store.update()
        source = source_utils.resolve_class(artifact_store.__class__)
        self.artifact_store_map[key] = UUIDSourceTuple(
            uuid=artifact_store.uuid, source=source
        )
        self.update()

    def delete_artifact_store(self, key: Text):
        """Delete an artifact_store.

        Args:
            key: Unique key of artifact_store.
        """
        s = self.get_artifact_store(key)  # check whether it exists
        s.delete()
        del self.artifact_store_map[key]
        self.update()
        logger.info(f"Deleted artifact_store with key: {key}.")

    def get_metadata_store(self, key: Text) -> BaseMetadataStore:
        """Return a single metadata store based on key.

        Args:
            key: Unique key of metadata store.

        Returns:
            Provider specified by key.
        """
        logger.debug(f"Fetching metadata_store with key {key}")
        if key not in self.metadata_store_map:
            raise DoesNotExistException(
                f"Provider of key `{key}` does not exist. "
                f"Available keys: {self.metadata_store_map.keys()}"
            )
        return mapping_utils.get_component_from_key(
            key, self.metadata_store_map
        )

    def register_metadata_store(
        self, key: Text, metadata_store: BaseMetadataStore
    ):
        """Register a metadata store.

        Args:
            metadata_store: Metadata store to be registered.
            key: Unique key for the metadata store.
        """
        logger.info(
            f"Registering provider with key {key}, details: "
            f"{metadata_store.dict()}"
        )
        if key in self.metadata_store_map:
            raise AlreadyExistsException(
                message=f"Artifact Store `{key}` already exists!"
            )

        # Add the mapping.
        metadata_store.update()
        source = source_utils.resolve_class(metadata_store.__class__)
        self.metadata_store_map[key] = UUIDSourceTuple(
            uuid=metadata_store.uuid, source=source
        )
        self.update()

    def delete_metadata_store(self, key: Text):
        """Delete a metadata store.

        Args:
            key: Unique key of metadata store.
        """
        s = self.get_metadata_store(key)  # check whether it exists
        s.delete()
        del self.metadata_store_map[key]
        self.update()
        logger.info(f"Deleted orchestrator with key: {key}.")

    def get_orchestrator(self, key: Text) -> BaseOrchestrator:
        """Return a single orchestrator based on key.

        Args:
            key: Unique key of orchestrator.

        Returns:
            Provider specified by key.
        """
        logger.debug(f"Fetching orchestrator with key {key}")
        if key not in self.orchestrator_map:
            raise DoesNotExistException(
                f"Provider of key `{key}` does not exist. "
                f"Available keys: {self.orchestrator_map.keys()}"
            )
        return mapping_utils.get_component_from_key(key, self.orchestrator_map)

    def register_orchestrator(self, key: Text, orchestrator: BaseOrchestrator):
        """Register an orchestrator.

        Args:
            orchestrator: Metadata store to be registered.
            key: Unique key for the orchestrator.
        """
        logger.info(
            f"Registering provider with key {key}, details: "
            f"{orchestrator.dict()}"
        )
        if key in self.orchestrator_map:
            raise AlreadyExistsException(
                message=f"Artifact Store `{key}` already exists!"
            )

        # Add the mapping.
        orchestrator.update()
        source = source_utils.resolve_class(orchestrator.__class__)
        self.orchestrator_map[key] = UUIDSourceTuple(
            uuid=orchestrator.uuid, source=source
        )
        self.update()

    def delete_orchestrator(self, key: Text):
        """Delete a orchestrator.

        Args:
            key: Unique key of orchestrator.
        """
        s = self.get_orchestrator(key)  # check whether it exists
        s.delete()
        del self.orchestrator_map[key]
        self.update()
        logger.info(f"Deleted orchestrator with key: {key}.")

    def delete(self):
        """Deletes the entire service. Dangerous operation"""
        for m in self.metadata_stores.values():
            m.delete()
        for a in self.artifact_stores.values():
            a.delete()
        for o in self.orchestrators.values():
            o.delete()
        super().delete()