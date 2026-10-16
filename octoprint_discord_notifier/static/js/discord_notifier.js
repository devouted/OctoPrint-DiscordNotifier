/*
 * Discord Notifier — settings panel view model.
 *
 * With custom_bindings=True all bindings in the template MUST go through
 * settingsViewModel (OctoPrint does not automatically bind the plugin's fields
 * to the plugin's own view model). Checkboxes/fields bind directly to
 * `settingsViewModel.settings.plugins.discord_notifier.*`, and this view model
 * only provides the logic for the "Send test" button.
 */
$(function () {
    function DiscordNotifierViewModel(parameters) {
        var self = this;

        self.settingsViewModel = parameters[0];

        self.testing = ko.observable(false);
        self.testResult = ko.observable(null); // null | "ok" | "error"
        self.testError = ko.observable("");

        self.testNotification = function () {
            self.testing(true);
            self.testResult(null);
            self.testError("");

            OctoPrint.simpleApiCommand("discord_notifier", "test", {})
                .done(function (response) {
                    if (response && response.success) {
                        self.testResult("ok");
                    } else {
                        self.testResult("error");
                        self.testError((response && response.error) || "Unknown error.");
                    }
                })
                .fail(function (xhr) {
                    self.testResult("error");
                    var msg = "Request failed.";
                    if (xhr && xhr.responseJSON && xhr.responseJSON.error) {
                        msg = xhr.responseJSON.error;
                    } else if (xhr && xhr.status) {
                        msg = "HTTP " + xhr.status;
                    }
                    self.testError(msg);
                })
                .always(function () {
                    self.testing(false);
                });
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: DiscordNotifierViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#settings_plugin_discord_notifier"]
    });
});
