package app.ledgera.shell

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationRailItem
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.ledgera.debts.DebtsScreen
import app.ledgera.debts.DebtsViewModel
import app.ledgera.budget.BudgetScreen
import app.ledgera.budget.BudgetViewModel
import app.ledgera.mandatory.MandatoryFileActions
import app.ledgera.mandatory.MandatoryScreen
import app.ledgera.mandatory.MandatoryViewModel
import app.ledgera.mandatory.NoMandatoryFileActions
import app.ledgera.operations.OperationsScreen
import app.ledgera.operations.OperationsFileActions
import app.ledgera.operations.NoOperationsFileActions
import app.ledgera.operations.OperationsViewModel
import app.ledgera.reports.ReportsScreen
import app.ledgera.reports.ReportsViewModel
import app.ledgera.reports.ReportsFileActions
import app.ledgera.reports.NoReportsFileActions
import app.ledgera.settings.SettingsScreen
import app.ledgera.settings.SettingsFileActions
import app.ledgera.settings.NoSettingsFileActions
import app.ledgera.settings.SettingsViewModel
import app.ledgera.ui.ToastHost
import app.ledgera.resources.Res
import app.ledgera.resources.ic_analytics
import app.ledgera.resources.ic_analytics_selected
import app.ledgera.resources.ic_budget
import app.ledgera.resources.ic_budget_selected
import app.ledgera.resources.ic_dashboard
import app.ledgera.resources.ic_dashboard_selected
import app.ledgera.resources.ic_debts
import app.ledgera.resources.ic_debts_selected
import app.ledgera.resources.ic_distribution
import app.ledgera.resources.ic_distribution_selected
import app.ledgera.resources.ic_mandatory
import app.ledgera.resources.ic_mandatory_selected
import app.ledgera.resources.ic_operations
import app.ledgera.resources.ic_operations_selected
import app.ledgera.resources.ic_reports
import app.ledgera.resources.ic_reports_selected
import app.ledgera.resources.ic_settings
import app.ledgera.resources.ic_settings_selected
import org.jetbrains.compose.resources.DrawableResource
import org.jetbrains.compose.resources.painterResource

@Composable
fun AppShell(
    viewModel: AppShellViewModel,
    operationsViewModel: OperationsViewModel,
    debtsViewModel: DebtsViewModel,
    mandatoryViewModel: MandatoryViewModel,
    settingsViewModel: SettingsViewModel,
    reportsViewModel: ReportsViewModel,
    budgetViewModel: BudgetViewModel,
    modifier: Modifier = Modifier,
    operationsFileActions: OperationsFileActions = NoOperationsFileActions,
    mandatoryFileActions: MandatoryFileActions = NoMandatoryFileActions,
    reportsFileActions: ReportsFileActions = NoReportsFileActions,
    settingsFileActions: SettingsFileActions = NoSettingsFileActions,
) {
    val state by viewModel.state.collectAsState()
    val operationsState by operationsViewModel.state.collectAsState()
    val debtsState by debtsViewModel.state.collectAsState()
    val mandatoryState by mandatoryViewModel.state.collectAsState()
    val settingsState by settingsViewModel.state.collectAsState()
    val reportsState by reportsViewModel.state.collectAsState()
    val budgetState by budgetViewModel.state.collectAsState()
    LaunchedEffect(Unit) {
        viewModel.refreshStatus()
        mandatoryViewModel.applyAutoPaymentsOnStartup()
    }
    LaunchedEffect(settingsState.restoreVersion) {
        if (settingsState.restoreVersion > 0) {
            operationsViewModel.refresh()
            debtsViewModel.refresh()
            mandatoryViewModel.refresh()
            reportsViewModel.refreshLookups()
            budgetViewModel.refresh()
        }
    }

    ToastHost(
        message = when (state.selectedSection) {
            DesktopSection.Operations -> operationsState.notice ?: operationsState.error
            DesktopSection.Debts -> debtsState.notice ?: debtsState.error
            DesktopSection.Mandatory -> mandatoryState.notice ?: mandatoryState.error
            DesktopSection.Settings -> settingsState.notice ?: settingsState.error
            DesktopSection.Reports -> reportsState.notice ?: reportsState.error
            DesktopSection.Budget -> budgetState.notice ?: budgetState.error
            else -> null
        },
        modifier = modifier.fillMaxSize(),
        onDismiss = {
            when (state.selectedSection) {
                DesktopSection.Operations -> operationsViewModel.clearFeedback()
                DesktopSection.Debts -> debtsViewModel.clearFeedback()
                DesktopSection.Mandatory -> mandatoryViewModel.clearFeedback()
                DesktopSection.Settings -> settingsViewModel.clearFeedback()
                DesktopSection.Reports -> reportsViewModel.clearFeedback()
                DesktopSection.Budget -> budgetViewModel.clearFeedback()
                else -> Unit
            }
        },
    ) {
        Row(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
            NavigationRail(
                modifier = Modifier.fillMaxHeight().width(110.dp),
                header = {
                    Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text("Ledgera", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                        Text("Beta.1", style = MaterialTheme.typography.labelMedium)
                    }
                },
            ) {
                state.sections.forEach { section ->
                    val selected = state.selectedSection == section
                    NavigationRailItem(
                        selected = selected,
                        onClick = { viewModel.select(section) },
                        icon = {
                            NavigationIcon(
                                icons = section.iconResources(),
                                selected = selected,
                            )
                        },
                        label = { Text(section.label) },
                        alwaysShowLabel = true,
                    )
                }
            }

            Column(Modifier.fillMaxSize()) {
                if (state.error != null || state.engineMessage.isMeaningfulStatus()) {
                    StatusBanner(state.engineMessage, state.error)
                }
                Surface(Modifier.fillMaxSize()) {
                    when (state.selectedSection) {
                        DesktopSection.Operations -> OperationsScreen(
                            operationsViewModel,
                            fileActions = operationsFileActions,
                        )
                        DesktopSection.Reports -> ReportsScreen(reportsViewModel, reportsFileActions)
                        DesktopSection.Analytics -> PendingSection(state.selectedSection)
                        DesktopSection.Dashboard -> PendingSection(state.selectedSection)
                        DesktopSection.Budget -> BudgetScreen(budgetViewModel)
                        DesktopSection.Debts -> DebtsScreen(debtsViewModel)
                        DesktopSection.Distribution -> PendingSection(state.selectedSection)
                        DesktopSection.Mandatory -> MandatoryScreen(
                            viewModel = mandatoryViewModel,
                            fileActions = mandatoryFileActions,
                        )
                        DesktopSection.Settings -> SettingsScreen(settingsViewModel, fileActions = settingsFileActions)
                    }
                }
            }
        }
        mandatoryState.autoPayPopup?.let { popup ->
            AlertDialog(
                onDismissRequest = mandatoryViewModel::closeAutoPayPopup,
                title = { Text(popup.title) },
                text = { Text(popup.message) },
                confirmButton = {
                    Button(onClick = mandatoryViewModel::closeAutoPayPopup) {
                        Text("OK")
                    }
                },
            )
        }
    }
}

private fun String.isMeaningfulStatus(): Boolean =
    trim().isNotEmpty() && !equals("ready", ignoreCase = true)

private data class NavigationIconResources(
    val outline: DrawableResource,
    val solid: DrawableResource,
)

private fun DesktopSection.iconResources(): NavigationIconResources = when (this) {
    DesktopSection.Operations -> NavigationIconResources(Res.drawable.ic_operations, Res.drawable.ic_operations_selected)
    DesktopSection.Reports -> NavigationIconResources(Res.drawable.ic_reports, Res.drawable.ic_reports_selected)
    DesktopSection.Analytics -> NavigationIconResources(Res.drawable.ic_analytics, Res.drawable.ic_analytics_selected)
    DesktopSection.Dashboard -> NavigationIconResources(Res.drawable.ic_dashboard, Res.drawable.ic_dashboard_selected)
    DesktopSection.Budget -> NavigationIconResources(Res.drawable.ic_budget, Res.drawable.ic_budget_selected)
    DesktopSection.Debts -> NavigationIconResources(Res.drawable.ic_debts, Res.drawable.ic_debts_selected)
    DesktopSection.Distribution -> NavigationIconResources(Res.drawable.ic_distribution, Res.drawable.ic_distribution_selected)
    DesktopSection.Mandatory -> NavigationIconResources(Res.drawable.ic_mandatory, Res.drawable.ic_mandatory_selected)
    DesktopSection.Settings -> NavigationIconResources(Res.drawable.ic_settings, Res.drawable.ic_settings_selected)
}

@Composable
private fun NavigationIcon(icons: NavigationIconResources, selected: Boolean) {
    val solidAlpha by animateFloatAsState(
        targetValue = if (selected) 1f else 0f,
        animationSpec = tween(durationMillis = 160),
        label = "navigation-icon-solid-alpha",
    )
    Box(Modifier.size(22.dp), contentAlignment = Alignment.Center) {
        Icon(
            painter = painterResource(icons.outline),
            contentDescription = null,
            modifier = Modifier.size(22.dp).alpha(1f - solidAlpha),
        )
        Icon(
            painter = painterResource(icons.solid),
            contentDescription = null,
            modifier = Modifier.size(22.dp).alpha(solidAlpha),
        )
    }
}

@Composable
private fun StatusBanner(message: String, error: String?) {
    val containerColor = if (error == null) {
        MaterialTheme.colorScheme.surfaceVariant
    } else {
        MaterialTheme.colorScheme.errorContainer
    }
    val textColor = if (error == null) {
        MaterialTheme.colorScheme.onSurfaceVariant
    } else {
        MaterialTheme.colorScheme.onErrorContainer
    }
    Row(
        Modifier.fillMaxWidth().background(containerColor).padding(horizontal = 20.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(message, color = textColor, style = MaterialTheme.typography.bodyMedium)
        error?.let { Text(it, color = textColor, style = MaterialTheme.typography.bodyMedium) }
    }
}

@Composable
private fun PendingSection(section: DesktopSection) {
    Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.TopStart) {
        Column(
            Modifier.fillMaxWidth().heightIn(min = 160.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(section.label, style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Bold)
            Text(
                "Beta.1 surface pending Rust UniFFI capability wiring.",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
