import pytest

from council.tools.architecture import analyze_architecture
from council.tools.code_analysis import analyze_imports


@pytest.mark.asyncio
async def test_analyze_imports_javascript(tmp_path):
    # Create a JS file
    js_file = tmp_path / "test.js"
    js_content = """
    import React from 'react';
    import { useState } from 'react';
    const utils = require('./utils');

    function App() {
        return <div />;
    }
    """
    js_file.write_text(js_content)

    # Pass base_path to allow access to tmp_path
    result = await analyze_imports(str(js_file), base_path=str(tmp_path))

    imports = result.get("imports", [])
    local = result.get("local_imports", [])
    external = result.get("external_imports", [])

    assert "react" in imports or "react" in external
    assert "./utils" in imports or "./utils" in local
    assert len(imports) >= 3


@pytest.mark.asyncio
async def test_analyze_imports_typescript(tmp_path):
    ts_file = tmp_path / "test.ts"
    ts_content = """
    import { Component } from '@angular/core';
    import { SharedService } from '../shared/service';

    @Component({})
    export class MyComponent {}
    """
    ts_file.write_text(ts_content)

    result = await analyze_imports(str(ts_file), base_path=str(tmp_path))

    imports = result.get("imports", [])

    assert "@angular/core" in imports
    assert "../shared/service" in imports


@pytest.mark.asyncio
async def test_analyze_architecture_typescript(tmp_path):
    ts_file = tmp_path / "complex.ts"
    # Create a file with many methods to trigger God Object detection
    methods = "\n".join([f"  method{i}() {{}}" for i in range(25)])
    ts_content = f"""
    import {{ A }} from 'a';

    class GodObject {{
    {methods}
    }}
    """
    ts_file.write_text(ts_content)

    result = await analyze_architecture(str(ts_file), base_path=str(tmp_path))

    anti_patterns = result.get("anti_patterns", [])

    assert any("God Object" in ap for ap in anti_patterns)


@pytest.mark.asyncio
async def test_analyze_architecture_java(tmp_path):
    java_file = tmp_path / "Test.java"
    java_content = """
    import java.util.List;
    import java.util.ArrayList;

    public class Test {
        public void method1() {}
    }
    """
    java_file.write_text(java_content)

    result = await analyze_imports(str(java_file), base_path=str(tmp_path))
    assert "java.util.List" in result.get("imports", [])

    result_arch = await analyze_architecture(str(java_file), base_path=str(tmp_path))
    # Just ensure it runs without error and returns dict
    assert isinstance(result_arch, dict)
