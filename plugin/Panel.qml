pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

Panel {
  id: root
  moduleName: "raiden-meixelysia.omaicon"
  ipcTarget: "raiden-meixelysia.omaicon"

  readonly property string cli: decodeURIComponent(String(Qt.resolvedUrl("../engine/omaicon.py")).replace(/^file:\/\//, ""))
  readonly property color foreground: bar ? bar.foreground : Commons.Color.foreground
  readonly property color urgent: bar ? bar.urgent : Commons.Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  property var info: null
  property string error: ""
  property string busy: ""
  property int cursor: -1
  property int paletteCursor: -1
  property bool showAll: false
  property string lastAction: ""
  property bool packDone: false

  readonly property var themes: info ? info.themes : []
  readonly property var palettes: info ? info.palettes : []
  readonly property int updateIndex: palettes.length
  readonly property string packDate: info && info.pack.date
    ? new Date(info.pack.date).toLocaleDateString(Qt.locale(Commons.I18n.formatLocale), Locale.ShortFormat) : ""
  readonly property int previewCount: 5
  readonly property bool hasMore: themes.length > previewCount
  readonly property var shown: showAll ? themes : themes.slice(0, previewCount)
  readonly property int toggleIndex: hasMore ? shown.length : -1
  readonly property string heroMeta: {
    if (!info) return ""
    for (var i = 0; i < themes.length; i++) {
      if (themes[i].name !== info.choice) continue
      return themes[i].name === "OmaPixIcon" ? themes[i].title + " · " + info.palette : themes[i].title
    }
    return info.choice
  }

  function load() {
    if (!statusProc.running) statusProc.running = true
  }

  function run(args, target) {
    if (busy !== "") return
    busy = target
    error = ""
    lastAction = args[0]
    actionProc.command = ["python3", "-B", cli].concat(args)
    console.log("omaicon: run " + JSON.stringify(args))
    actionProc.running = true
  }

  function use(name) {
    if (info && name === info.choice && name !== "OmaPixIcon") return
    run(["use", name], name)
  }

  function setPalette(name) {
    run(["palette", name], "OmaPixIcon")
  }

  function updatePack() {
    run(["update-pack"], "OmaPixIcon")
  }

  function point(index) {
    if (cursor !== index) paletteCursor = -1
    cursor = index
  }

  function move(dx, dy) {
    if (shown.length === 0) return
    var last = hasMore ? toggleIndex : shown.length - 1
    if (dy !== 0 || cursor < 0) {
      point(Math.max(0, Math.min(last, cursor + (cursor < 0 ? 0 : dy))))
      return
    }
    if (cursor >= shown.length || shown[cursor].name !== "OmaPixIcon") return
    paletteCursor = Math.max(0, Math.min(updateIndex, paletteCursor + dx))
  }

  function activate() {
    if (cursor < 0) return
    if (cursor === toggleIndex) toggleAll()
    else if (paletteCursor === updateIndex) updatePack()
    else if (paletteCursor >= 0) setPalette(palettes[paletteCursor].name)
    else use(shown[cursor].name)
  }

  function toggleAll() {
    showAll = !showAll
    point(toggleIndex)
  }

  function lastLine(text) {
    var lines = String(text || "").trim().split("\n")
    return lines[lines.length - 1]
  }

  onOpenedChanged: {
    if (!opened) {
      showAll = false
      return
    }
    cursor = -1
    paletteCursor = -1
    load()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  Process {
    id: statusProc
    command: ["python3", "-B", root.cli, "status"]
    stdout: StdioCollector { id: statusOut; waitForEnd: true }
    stderr: StdioCollector { id: statusErr; waitForEnd: true }
    onExited: function(exitCode) {
      if (exitCode !== 0) {
        console.warn("omaicon: status exited " + exitCode + ": " + statusErr.text)
        root.error = root.lastLine(statusErr.text) || ("status exited " + exitCode)
        return
      }
      try {
        root.info = JSON.parse(statusOut.text)
      } catch (e) {
        console.warn("omaicon: bad status JSON: " + e + ": " + statusOut.text.slice(0, 200))
        root.error = "bad status: " + e
      }
    }
  }

  Process {
    id: actionProc
    stderr: StdioCollector { id: actionErr; waitForEnd: true }
    onExited: function(exitCode) {
      console.log("omaicon: exit " + exitCode + "\n" + actionErr.text)
      if (exitCode !== 0) root.error = root.lastLine(actionErr.text) || ("exited " + exitCode)
      else if (root.lastAction === "update-pack") {
        root.packDone = true
        packDoneTimer.restart()
      }
      root.busy = ""
      root.load()
    }
  }

  Timer { id: packDoneTimer; interval: 1600; onTriggered: root.packDone = false }

  // An app update can rewrite its launcher with a hard-coded icon path. fix-launchers only writes
  // launchers still on a path, so its own edits end the loop.
  Process {
    id: launcherProc
    command: ["python3", "-B", root.cli, "fix-launchers"]
    stderr: StdioCollector { id: launcherErr; waitForEnd: true }
    onExited: function(exitCode) {
      if (exitCode !== 0) console.warn("omaicon: fix-launchers exited " + exitCode + ": " + launcherErr.text)
      else if (launcherErr.text) console.log(launcherErr.text)
    }
  }

  Timer {
    id: launcherDebounce
    interval: 3000
    running: true
    onTriggered: if (!launcherProc.running) launcherProc.running = true
  }

  Connections {
    target: DesktopEntries.applications
    function onValuesChanged() { launcherDebounce.restart() }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰀻"
    onPressed: function(buttonCode) { if (buttonCode === Qt.LeftButton) root.toggle() }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: panel.loadedContent
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight, Style.space(640))

    content: PanelKeyCatcher {
      anchors.fill: parent
      implicitHeight: column.implicitHeight
      onMoveRequested: function(dx, dy) { root.move(dx, dy) }
      onActivateRequested: root.activate()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: column
          width: parent.width
          spacing: Style.space(16)

          PanelHero {
            width: parent.width
            title: strings.t("title")
            meta: root.heroMeta
            foreground: root.foreground
            fontFamily: root.fontFamily
            iconComponent: Component {
              Text {
                textFormat: Text.PlainText
                text: button.text
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.display
              }
            }
          }

          Text {
            visible: root.error !== ""
            width: parent.width
            textFormat: Text.PlainText
            text: root.error
            color: root.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.Wrap
          }

          PanelSeparator { foreground: root.foreground }

          Column {
            width: parent.width
            spacing: Style.space(4)

            Repeater {
              model: root.shown
              ThemeRow { width: column.width }
            }

            Button {
              visible: root.hasMore
              width: parent.width
              leftAlign: true
              iconText: root.showAll ? "\uf077" : "\uf078"
              text: root.showAll ? strings.t("showLess") : strings.tn("viewAll", root.themes.length).arg(Commons.I18n.formatNumber(root.themes.length))
              foreground: root.foreground
              fontFamily: root.fontFamily
              hasCursor: root.cursor === root.toggleIndex
              onHovered: function(h) { if (h) root.point(root.toggleIndex) }
              onClicked: root.toggleAll()
            }
          }
        }
      }
    }
  }

  component ThemeRow: Column {
    id: row
    required property var modelData
    required property int index
    readonly property bool omapix: modelData.name === "OmaPixIcon"
    readonly property bool active: root.info !== null && root.info.choice === modelData.name
    readonly property bool working: root.busy === modelData.name
    readonly property bool revealed: omapix && root.cursor === index

    CursorSurface {
      width: parent.width
      implicitHeight: Style.space(46)
      hasCursor: root.cursor === row.index
      current: row.active
      foreground: root.foreground

      Text {
        anchors.left: parent.left
        anchors.leftMargin: Style.spacing.rowPaddingX
        anchors.right: previews.left
        anchors.rightMargin: Style.spacing.rowGap
        anchors.verticalCenter: parent.verticalCenter
        textFormat: Text.PlainText
        text: row.modelData.title
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        font.bold: row.active
        elide: Text.ElideRight
      }

      Row {
        id: previews
        anchors.right: parent.right
        anchors.rightMargin: Style.spacing.rowPaddingX
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(8)

        Repeater {
          model: row.modelData.previews
          SizedImage {
            required property string modelData
            width: Style.space(22)
            height: width
            url: Commons.Util.fileUrl(modelData)
          }
        }

        SequentialAnimation on opacity {
          running: row.working
          loops: Animation.Infinite
          alwaysRunToEnd: true
          NumberAnimation { to: 0.35; duration: Style.duration(420); easing.type: Easing.InOutSine }
          NumberAnimation { to: 1.0; duration: Style.duration(420); easing.type: Easing.InOutSine }
        }
      }

      MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: root.busy === "" ? Qt.PointingHandCursor : Qt.BusyCursor
        onEntered: root.point(row.index)
        onClicked: root.use(row.modelData.name)
      }
    }

    Item {
      width: parent.width
      height: row.revealed ? strip.height + Style.space(6) : 0
      opacity: row.revealed ? 1 : 0
      clip: true
      visible: height > 0

      Behavior on height { NumberAnimation { duration: Style.duration(180); easing.type: Easing.Bezier; easing.bezierCurve: Style.easeOut } }
      Behavior on opacity { NumberAnimation { duration: Style.duration(140); easing.type: Easing.OutCubic } }

      ListView {
        id: strip
        y: Style.space(6)
        x: Style.spacing.rowPaddingX
        width: update.x - x - Style.space(8)
        height: Style.space(40)
        orientation: ListView.Horizontal
        spacing: Style.space(4)
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: row.omapix ? root.palettes : []
        currentIndex: root.paletteCursor
        highlightFollowsCurrentItem: false
        onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(currentIndex, ListView.Contain)

        WheelHandler {
          onWheel: function(event) {
            var delta = event.angleDelta.y !== 0 ? event.angleDelta.y : event.angleDelta.x
            strip.contentX = Math.max(strip.originX, Math.min(strip.originX + strip.contentWidth - strip.width, strip.contentX - delta))
          }
        }

        delegate: Item {
          id: chip
          required property var modelData
          required property int index
          readonly property bool chosen: root.info !== null && root.info.palette === modelData.name
          readonly property bool hot: chipMouse.containsMouse || root.paletteCursor === index
          width: Style.space(40)
          height: width

          SizedImage {
            anchors.centerIn: parent
            width: Style.space(28)
            height: width
            url: Commons.Util.fileUrl(chip.modelData.preview)
            opacity: chip.chosen || chip.hot ? 1 : 0.4
            scale: chip.hot ? 1.12 : 1
            Behavior on opacity { NumberAnimation { duration: Style.duration(120); easing.type: Easing.OutCubic } }
            Behavior on scale { NumberAnimation { duration: Style.duration(120); easing.type: Easing.OutCubic } }
          }

          Rectangle {
            visible: chip.chosen
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            width: Style.space(12)
            height: Style.space(2)
            radius: height / 2
            color: Commons.Color.accent
          }

          MouseArea {
            id: chipMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: root.busy === "" ? Qt.PointingHandCursor : Qt.BusyCursor
            onEntered: root.paletteCursor = chip.index
            onClicked: root.setPalette(chip.modelData.name)
          }

          PanelToolTip {
            visible: chipMouse.containsMouse
            text: chip.modelData.name
            fontFamily: root.fontFamily
          }
        }
      }

      PanelActionButton {
        id: update
        anchors.right: parent.right
        anchors.rightMargin: Style.spacing.rowPaddingX
        anchors.verticalCenter: strip.verticalCenter
        size: Style.space(34)
        fontSize: Style.font.heading
        iconText: root.packDone ? "\uDB80\uDD2C" : "\uDB81\uDEB0"
        foreground: root.foreground
        fontFamily: root.fontFamily
        enabled: root.busy === ""
        hasCursor: root.paletteCursor === root.updateIndex
        tooltipText: strings.t("updatePack").arg(root.packDate)
        onHovered: function(h) { if (h) root.paletteCursor = root.updateIndex }
        onClicked: root.updatePack()
      }
    }
  }
}
