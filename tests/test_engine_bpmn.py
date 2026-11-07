"""The execution XML subset rejects executable extensions rather than stripping them."""

import pytest
from fastapi import HTTPException

NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
SERIAL = f'''<definitions xmlns="{NS}" targetNamespace="urn:synthetic"><process id="sandbox" isExecutable="true">
<startEvent id="s"/><userTask id="a" name="A"/><endEvent id="e"/>
<sequenceFlow id="f1" sourceRef="s" targetRef="a"/><sequenceFlow id="f2" sourceRef="a" targetRef="e"/>
</process></definitions>'''
PARALLEL = f'''<definitions xmlns="{NS}" targetNamespace="urn:synthetic"><process id="parallel" isExecutable="true">
<startEvent id="s"/><parallelGateway id="fork"/><userTask id="a"/><userTask id="b"/>
<parallelGateway id="join"/><endEvent id="e"/>
<sequenceFlow id="f1" sourceRef="s" targetRef="fork"/>
<sequenceFlow id="f2" sourceRef="fork" targetRef="a"/><sequenceFlow id="f3" sourceRef="fork" targetRef="b"/>
<sequenceFlow id="f4" sourceRef="a" targetRef="join"/><sequenceFlow id="f5" sourceRef="b" targetRef="join"/>
<sequenceFlow id="f6" sourceRef="join" targetRef="e"/>
</process></definitions>'''


def test_serial_and_structured_parallel_preserve_identity():
    from app.services.engine_bpmn import inspect_xml

    assert inspect_xml(SERIAL)["tasks"] == ["a"]
    parallel = inspect_xml(PARALLEL)
    assert parallel["process_key"] == "parallel" and parallel["tasks"] == ["a", "b"]
    assert {n["node_type"] for n in parallel["nodes"]} == {"START", "END", "APPROVAL", "PARALLEL"}


@pytest.mark.parametrize(
    "xml",
    [
        SERIAL.replace('<userTask id="a"', '<userTask xmlns:x="urn:evil" x:class="Evil" id="a"'),
        SERIAL.replace(
            '<userTask id="a" name="A"/>', '<scriptTask id="a"><script>bad()</script></scriptTask>'
        ),
        SERIAL.replace(
            '<startEvent id="s"/>', '<startEvent id="s"><timerEventDefinition/></startEvent>'
        ),
        SERIAL.replace(
            '<userTask id="a" name="A"/>',
            '<userTask id="a"><extensionElements><unknown/></extensionElements></userTask>',
        ),
        SERIAL.replace('targetRef="e"', 'targetRef="s"'),
        SERIAL.replace("<process ", '<process xmlns:f="http://flowable.org/bpmn" f:async="true" '),
        '<!DOCTYPE x [<!ENTITY external SYSTEM "file:///secret">]>' + SERIAL,
        PARALLEL.replace('sourceRef="b" targetRef="join"', 'sourceRef="b" targetRef="e"'),
        SERIAL.replace('<endEvent id="e"/>', '<endEvent id="e"/><userTask id="orphan"/>'),
        SERIAL.replace('name="A"', 'name="${evil}"'),
        SERIAL.replace(
            '<userTask id="a" name="A"/>',
            '<userTask id="a" name="A"><userTask id="nested"/></userTask>',
        ),
        SERIAL.replace(
            '<userTask id="a" name="A"/>',
            '<userTask id="a" name="A"><extensionElements><userTask id="hidden"/></extensionElements></userTask>',
        ),
    ],
)
def test_unsafe_or_unverified_construct_is_rejected(xml):
    from app.services.engine_bpmn import inspect_xml

    with pytest.raises(HTTPException) as error:
        inspect_xml(xml)
    assert error.value.status_code == 400


def test_legacy_parallel_import_still_rejected():
    from app.services.bpmn import import_bpmn

    with pytest.raises(HTTPException):
        import_bpmn(PARALLEL)


def test_flowable_xml_lifecycle_and_frozen_identity(client):
    from app.core.database import SessionLocal
    from app.models.process import ProcessModelVersion

    made = client.post(
        "/api/v1/process-map", json={"code": "L3-R3-XML", "name": "沙箱并行", "level": 3}
    )
    assert made.status_code == 201
    pid = made.json()["id"]
    try:
        saved = client.post(
            f"/api/v1/processes/{pid}/bpmn",
            json={"xml": PARALLEL, "execution_provider": "FLOWABLE"},
        )
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["execution_provider"] == "FLOWABLE"
        patched = client.patch(
            f"/api/v1/processes/{pid}/design/nodes/a",
            json={"duration_minutes": 12, "expected_version": body["version"]},
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["execution_provider"] == "FLOWABLE"
        body = patched.json()
        version_id = body["version_id"]
        frozen = client.post(
            f"/api/v1/processes/{pid}/design/freeze",
            json={"expected_version": body["version"], "note": "固定沙箱模型"},
        )
        assert frozen.status_code == 200, frozen.text
        changed = client.post(
            f"/api/v1/processes/{pid}/bpmn", json={"xml": SERIAL, "execution_provider": "FLOWABLE"}
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["version_id"] != version_id
        with SessionLocal() as db:
            row = db.get(ProcessModelVersion, version_id)
            assert row.execution_provider == "FLOWABLE" and row.bpmn_xml == PARALLEL
    finally:
        client.delete(f"/api/v1/process-map/{pid}")
