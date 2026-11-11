"""Inventory the installed runtime closure as SPDX 2.3; exclude dev/system extras."""

import json
from datetime import UTC, datetime
from importlib.metadata import distribution
from pathlib import Path
from uuid import uuid4

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

queue = ["backloger"]
found = {}
relationships = []
while queue:
    name = canonicalize_name(queue.pop())
    if name in found:
        continue
    package = distribution(name)
    found[name] = package
    for value in package.requires or []:
        requirement = Requirement(value)
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        dependency = canonicalize_name(requirement.name)
        queue.append(dependency)
        relationships.append(
            {
                "spdxElementId": f"SPDXRef-{name}",
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": f"SPDXRef-{dependency}",
            }
        )
result = {
    "spdxVersion": "SPDX-2.3",
    "dataLicense": "CC0-1.0",
    "SPDXID": "SPDXRef-DOCUMENT",
    "name": "Backloger runtime",
    "documentNamespace": f"https://softctrl.com/backloger/sbom/{uuid4()}",
    "creationInfo": {
        "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "creators": ["Tool: Backloger-sbom-0.1.0"],
    },
    "packages": [
        {
            "SPDXID": f"SPDXRef-{name}",
            "name": name,
            "versionInfo": package.version,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": package.metadata.get("License-Expression", "NOASSERTION"),
            "copyrightText": "NOASSERTION",
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": f"pkg:pypi/{name}@{package.version}",
                }
            ],
        }
        for name, package in sorted(found.items())
    ],
    "relationships": [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-backloger",
        },
        *relationships,
    ],
}
directory = Path("dist")
directory.mkdir(exist_ok=True)
(directory / "sbom.spdx.json").write_text(json.dumps(result, indent=2) + "\n")
(directory / "requirements-runtime.txt").write_text(
    "".join(
        f"{name}=={package.version}\n"
        for name, package in sorted(found.items())
        if name != "backloger"
    )
)
print(f"SPDX: {len(found)} pacotes em dist/sbom.spdx.json")
