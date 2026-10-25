#!/usr/bin/env python3
"""Small deterministic Xcode project generator; no globally installed generator needed."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
objects = []
def ident(name): return hashlib.sha1(name.encode()).hexdigest()[:24].upper()
def add(name, content):
    key = ident(name)
    objects.append(f'{key} = {{ {content} }};')
    return key
def array(items): return '(' + ', '.join(items) + (',' if items else '') + ')'

app_files, app_build = [], []
for path in sorted((ROOT / 'iosApp/CircleGuard').glob('*.swift')):
    ref = add('file:'+path.name, f'isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = "{path.name}"; sourceTree = "<group>";')
    app_files.append(ref)
    app_build.append(add('build:'+path.name, f'isa = PBXBuildFile; fileRef = {ref};'))
for name, kind in [('Info.plist','text.plist.xml'), ('Push.entitlements','text.plist.entitlements')]:
    app_files.append(add(name, f'isa = PBXFileReference; lastKnownFileType = {kind}; path = "{name}"; sourceTree = "<group>";'))
assets = add('assets', 'isa = PBXFileReference; lastKnownFileType = folder.assetcatalog; path = Assets.xcassets; sourceTree = "<group>";')
app_files.append(assets)
assets_build = add('assets-build', f'isa = PBXBuildFile; fileRef = {assets};')
test_ref = add('test-file', 'isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = CircleGuardUITests.swift; sourceTree = "<group>";')
test_build = add('test-build', f'isa = PBXBuildFile; fileRef = {test_ref};')
app_product = add('app-product', 'isa = PBXFileReference; explicitFileType = wrapper.application; path = CircleGuard.app; sourceTree = BUILT_PRODUCTS_DIR;')
test_product = add('test-product', 'isa = PBXFileReference; explicitFileType = wrapper.cfbundle; path = CircleGuardUITests.xctest; sourceTree = BUILT_PRODUCTS_DIR;')
app_group = add('app-group', f'isa = PBXGroup; path = CircleGuard; children = {array(app_files)}; sourceTree = "<group>";')
test_group = add('test-group', f'isa = PBXGroup; path = CircleGuardUITests; children = ({test_ref}); sourceTree = "<group>";')
products = add('products', f'isa = PBXGroup; name = Products; children = ({app_product}, {test_product}); sourceTree = "<group>";')
main = add('main', f'isa = PBXGroup; children = ({app_group}, {test_group}, {products}); sourceTree = "<group>";')
sources = add('sources', f'isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = {array(app_build)}; runOnlyForDeploymentPostprocessing = 0;')
test_sources = add('test-sources', f'isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = ({test_build}); runOnlyForDeploymentPostprocessing = 0;')
frameworks = add('frameworks', 'isa = PBXFrameworksBuildPhase; buildActionMask = 2147483647; files = (); runOnlyForDeploymentPostprocessing = 0;')
resources = add('resources', f'isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = ({assets_build}); runOnlyForDeploymentPostprocessing = 0;')
script = 'set -e\\nif [ "$PLATFORM_NAME" = "iphonesimulator" ]; then TARGET=IosSimulatorArm64; else TARGET=IosArm64; fi\\n"$SRCROOT/../gradlew" ":shared:link${CONFIGURATION}Framework${TARGET}"\\n'
script = script.replace('"', '\\"')
build_kotlin = add('kotlin', f'isa = PBXShellScriptBuildPhase; buildActionMask = 2147483647; files = (); inputPaths = (); outputPaths = (); name = "Build shared Kotlin"; shellPath = /bin/bash; shellScript = "{script}"; runOnlyForDeploymentPostprocessing = 0; alwaysOutOfDate = 1;')

def configs(prefix, settings):
    result = []
    for config in ['Debug', 'Release']:
        common = 'SWIFT_VERSION = 5.0; IPHONEOS_DEPLOYMENT_TARGET = 17.0; SDKROOT = iphoneos; ARCHS = arm64; TARGETED_DEVICE_FAMILY = "1,2"; ENABLE_USER_SCRIPT_SANDBOXING = NO;'
        flags = 'SWIFT_OPTIMIZATION_LEVEL = "-Onone"; SWIFT_ACTIVE_COMPILATION_CONDITIONS = DEBUG;' if config == 'Debug' else 'SWIFT_OPTIMIZATION_LEVEL = "-O";'
        result.append(add(prefix+config, f'isa = XCBuildConfiguration; name = {config}; buildSettings = {{ {common} {flags} {settings(config)} }};'))
    return add(prefix+'configs', f'isa = XCConfigurationList; buildConfigurations = {array(result)}; defaultConfigurationIsVisible = 0; defaultConfigurationName = Debug;')

project_configs = configs('project', lambda _: 'CLANG_ENABLE_MODULES = YES; CODE_SIGN_STYLE = Automatic;')
app_configs = configs('app', lambda c: f'''
    PRODUCT_NAME = CircleGuard; PRODUCT_BUNDLE_IDENTIFIER = app.circleguard.ios;
    INFOPLIST_FILE = CircleGuard/Info.plist;
    ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;
    "FRAMEWORK_SEARCH_PATHS[sdk=iphonesimulator*]" = "$(SRCROOT)/../shared/build/bin/iosSimulatorArm64/{c.lower()}Framework";
    "FRAMEWORK_SEARCH_PATHS[sdk=iphoneos*]" = "$(SRCROOT)/../shared/build/bin/iosArm64/{c.lower()}Framework";
    OTHER_LDFLAGS = ("$(inherited)", "-framework", Shared, "-lc++");
    LD_RUNPATH_SEARCH_PATHS = ("$(inherited)", "@executable_path/Frameworks");
''')
test_configs = configs('test', lambda _: 'PRODUCT_NAME = CircleGuardUITests; PRODUCT_BUNDLE_IDENTIFIER = app.circleguard.uitests; GENERATE_INFOPLIST_FILE = YES; TEST_TARGET_NAME = CircleGuard;')
app_target = add('app-target', f'isa = PBXNativeTarget; name = CircleGuard; productName = CircleGuard; productType = "com.apple.product-type.application"; buildConfigurationList = {app_configs}; buildPhases = ({build_kotlin}, {sources}, {frameworks}, {resources}); buildRules = (); dependencies = (); productReference = {app_product};')
proxy = add('proxy', f'isa = PBXContainerItemProxy; containerPortal = {ident("project")}; proxyType = 1; remoteGlobalIDString = {app_target}; remoteInfo = CircleGuard;')
dependency = add('dependency', f'isa = PBXTargetDependency; target = {app_target}; targetProxy = {proxy};')
test_target = add('test-target', f'isa = PBXNativeTarget; name = CircleGuardUITests; productName = CircleGuardUITests; productType = "com.apple.product-type.bundle.ui-testing"; buildConfigurationList = {test_configs}; buildPhases = ({test_sources}); buildRules = (); dependencies = ({dependency}); productReference = {test_product};')
project = add('project', f'isa = PBXProject; attributes = {{ LastUpgradeCheck = 1600; }}; buildConfigurationList = {project_configs}; compatibilityVersion = "Xcode 14.0"; developmentRegion = en; knownRegions = (en, Base); mainGroup = {main}; productRefGroup = {products}; projectDirPath = ""; projectRoot = ""; targets = ({app_target}, {test_target});')
dest = ROOT / 'iosApp/CircleGuard.xcodeproj'
dest.mkdir(exist_ok=True)
(dest / 'project.pbxproj').write_text('// !$*UTF8*$!\n{ archiveVersion = 1; classes = {}; objectVersion = 56; objects = {\n' + '\n'.join(objects) + f'\n}}; rootObject = {project}; }}\n')
schemes = dest / 'xcshareddata/xcschemes'
schemes.mkdir(parents=True, exist_ok=True)
def reference(target, name, product):
    return f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{target}" BuildableName="{product}" BlueprintName="{name}" ReferencedContainer="container:CircleGuard.xcodeproj"/>'
app_ref = reference(app_target, 'CircleGuard', 'CircleGuard.app')
test_ref = reference(test_target, 'CircleGuardUITests', 'CircleGuardUITests.xctest')
(schemes / 'CircleGuard.xcscheme').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="1600" version="1.3">
  <BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries>
    <BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">{app_ref}</BuildActionEntry>
  </BuildActionEntries></BuildAction>
  <TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES"><Testables><TestableReference skipped="NO">{test_ref}</TestableReference></Testables></TestAction>
  <LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" allowLocationSimulation="YES"><BuildableProductRunnable runnableDebuggingMode="0">{app_ref}</BuildableProductRunnable></LaunchAction>
  <ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES" savedToolIdentifier="" useCustomWorkingDirectory="NO" debugDocumentVersioning="YES"><BuildableProductRunnable runnableDebuggingMode="0">{app_ref}</BuildableProductRunnable></ProfileAction>
  <AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>''')
print(dest)
