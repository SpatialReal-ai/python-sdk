from ten_runtime import (  # pylint: disable=import-error
    Addon,
    TenEnv,
    register_addon_as_extension,
)

from .extension import SpatialRealAvatarExtension


@register_addon_as_extension("spatialreal_avatar_python")
class SpatialRealAvatarExtensionAddon(Addon):
    def on_create_instance(self, ten_env: TenEnv, name: str, context) -> None:
        ten_env.log_info("on_create_instance")
        ten_env.on_create_instance_done(SpatialRealAvatarExtension(name), context)
