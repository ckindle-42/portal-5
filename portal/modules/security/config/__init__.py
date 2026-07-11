"""Reserved for the security module's config surface (BUILD-SPEC-PORTAL-MODULES-V1
Slice 5: "the security slices of config/portal.yaml + backends.yaml").

Not populated yet — there is no existing isolated Python config-loader to
re-export. Security-relevant config (seat models, workspace routing,
PROMOTE_POLICY) lives inline in the shared config/portal.yaml and
config/backends.yaml, loaded by portal.platform.inference.config /
cluster_backends alongside every other module's config, not as a
standalone security-only unit. Extracting a dedicated loader here would
be new code, not a relocation — out of scope for a structure-only slice.
"""
