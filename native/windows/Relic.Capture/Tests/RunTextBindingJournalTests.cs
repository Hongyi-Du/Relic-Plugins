using System.Text.Json.Nodes;
using Relic;
using Xunit;

namespace Relic.Capture.Tests;

public sealed class RunTextBindingJournalTests
{
    // Mock observations test receipt policy only. Actual SDK binding behavior is
    // evidenced separately by d7b164c's 19 CI probe processes and future captures.
    private static JsonObject State(string text = "initial 中") => new()
    {
        ["source_text"] = RunTextBindingJournal.Text(text), ["target_text"] = RunTextBindingJournal.Text(text),
        ["source_target_utf16_equal"] = true, ["source_has_ui_thread_access"] = true, ["target_has_ui_thread_access"] = true,
        ["target_is_loaded"] = false, ["target_xaml_root_is_null"] = true, ["target_visual_parent_is_null"] = true,
        ["binding_source_same_run"] = true, ["binding_mode_one_way"] = true, ["binding_path_text"] = true,
        ["callback_registered"] = true, ["binding_expression_present"] = true,
        ["expression_data_item_same_run"] = true, ["expression_parent_binding_same_object"] = true
    };

    [Fact]
    public void InitializationIsSeparateAndChangeThenRestoreAdvancesBothSourceRevisions()
    {
        var revision = 0; var failures = new List<string>();
        var journal = new RunTextBindingJournal(17, 1, () => revision++, failures.Add);
        var initial = State(); initial["binding_expression_present"] = false;
        initial["expression_data_item_same_run"] = null; initial["expression_parent_binding_same_object"] = null;
        journal.Callback(initial, true, true, 2);
        Assert.Equal(0, revision);
        journal.Installed(State(), 3);
        journal.Callback(State("temporary 瞬时"), true, true, 4);
        journal.Callback(State(), true, true, 5);
        Assert.Equal(2, revision); Assert.Empty(failures);
        Assert.True(journal.Check(State(), 6));
        Assert.Equal(1L, journal.Receipt["initialization_callback_count"]!.GetValue<long>());
        Assert.Equal(new[] { "installation", "observing", "observing" }, journal.Receipt["callbacks"]!.AsArray()
            .Select(value => value!["phase"]!.GetValue<string>()).ToArray());
        Assert.False(journal.Receipt["frame_continuity_supplied"]!.GetValue<bool>());
        Assert.False(journal.Receipt["canonical_geometry_supplied"]!.GetValue<bool>());
    }

    [Fact]
    public void EmptyInitialTextDoesNotInventARequiredInitializationCallback()
    {
        var journal = new RunTextBindingJournal(17, 1, () => throw new Exception("Unexpected revision"), _ => { });
        journal.Installed(State(""), 2);
        Assert.True(journal.Check(State(""), 3));
        Assert.Equal(0L, journal.Receipt["initialization_callback_count"]!.GetValue<long>());
    }

    [Theory]
    [InlineData("binding_source_same_run")]
    [InlineData("expression_data_item_same_run")]
    [InlineData("expression_parent_binding_same_object")]
    [InlineData("source_has_ui_thread_access")]
    [InlineData("target_has_ui_thread_access")]
    [InlineData("target_xaml_root_is_null")]
    [InlineData("target_visual_parent_is_null")]
    [InlineData("callback_registered")]
    [InlineData("binding_mode_one_way")]
    [InlineData("binding_path_text")]
    public void LostIdentityMountingOrCallbackCoverageRemainsFailedAfterValuesRestore(string field)
    {
        var failures = new List<string>(); var journal = new RunTextBindingJournal(17, 1, () => { }, failures.Add);
        journal.Installed(State(), 2);
        var invalid = State(); invalid[field] = false;
        Assert.False(journal.Check(invalid, 3));
        Assert.False(journal.Check(State(), 4)); Assert.NotEmpty(failures);
    }

    [Fact]
    public void MountedTargetAndMissingMeasurementCannotBeAccepted()
    {
        var mounted = State(); mounted["target_is_loaded"] = true;
        var journal = new RunTextBindingJournal(17, 1, () => { }, _ => { });
        journal.Installed(mounted, 2); Assert.False(journal.Check(State(), 3));
        var missing = State(); missing.Remove("target_is_loaded");
        var other = new RunTextBindingJournal(18, 1, () => { }, _ => { });
        other.Installed(missing, 2); Assert.False(other.Check(State(), 3));
    }

    [Fact]
    public void FailedCallbackReadOrWrongSenderStillRecordsTheSourceRevisionAndFailure()
    {
        var revision = 0; var failures = new List<string>();
        var journal = new RunTextBindingJournal(17, 1, () => revision++, failures.Add);
        journal.Installed(State(), 2);
        journal.Callback(null, true, true, 3);
        journal.Callback(State(), false, true, 4);
        journal.Callback(State(), true, false, 5);
        Assert.Equal(3, revision); Assert.False(journal.Check(State(), 6));
        Assert.Equal(3, journal.Receipt["callbacks"]!.AsArray().Count); Assert.NotEmpty(failures);
    }

    [Fact]
    public void RawUtf16DistinguishesSurrogateCodeUnitsAndMismatchedTarget()
    {
        var actual = "甲\U0001F600\U00010437乙\uD800";
        var text = RunTextBindingJournal.Text(actual);
        Assert.Equal(7, text["utf16_length"]!.GetValue<int>());
        Assert.Equal(new byte[] { 0x32, 0x75, 0x3D, 0xD8, 0x00, 0xDE, 0x01, 0xD8, 0x37, 0xDC, 0x59, 0x4E, 0x00, 0xD8 },
            Convert.FromBase64String(text["utf16_le_base64"]!.GetValue<string>()));
        var journal = new RunTextBindingJournal(17, 1, () => { }, _ => { });
        journal.Installed(State(actual), 2);
        Assert.True(journal.Check(State(actual), 3));
        var different = State(actual); different["target_text"] = RunTextBindingJournal.Text(actual[..^1] + "\uFFFD");
        // Even a contradictory equal flag cannot override the actual raw bytes.
        Assert.False(journal.Check(different, 4));
    }

    [Fact]
    public void CleanupDisablesAvailabilityAndUnexpectedCallbacksAreRetained()
    {
        var revision = 0; var failures = new List<string>();
        var journal = new RunTextBindingJournal(17, 1, () => revision++, failures.Add);
        journal.Installed(State(), 2); journal.BeginCleanup(State(), 3);
        Assert.False(journal.Check(State(), 4));
        journal.Callback(State(), true, true, 5);
        Assert.Equal(0, revision); Assert.NotEmpty(failures);
        Assert.Equal("cleanup", journal.Receipt["callbacks"]![0]!["phase"]!.GetValue<string>());
    }
}
